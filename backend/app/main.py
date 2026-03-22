"""
backend/app/main.py
FastAPI application entry point.
All terrain endpoints return 501 until the data pipeline has run.
"""
import html
import re
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import (
    PROJECT_VERSION, CORS_ORIGINS,
    LLM_RATE_LIMIT_INTERVAL_SECONDS,
)
from .routers import journal as journal_router

app = FastAPI(
    title="Latent Language Explorer V2",
    version=PROJECT_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)

app.include_router(journal_router.router)

# In-memory rate limiting state (per process)
_last_llm_call: float = 0.0


# ── Health & config ───────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": PROJECT_VERSION}


@app.get("/api/config")
async def get_config():
    """Return non-sensitive configuration values for the frontend."""
    from .config import (
        DESERT_GATE_THRESHOLD, DESERT_SHALLOW_THRESHOLD,
        LLM_RATE_LIMIT_PER_HOUR, PROBE_STEPS,
    )
    return {
        "desert_gate_threshold":   DESERT_GATE_THRESHOLD,
        "desert_shallow_threshold": DESERT_SHALLOW_THRESHOLD,
        "llm_rate_limit_per_hour": LLM_RATE_LIMIT_PER_HOUR,
        "probe_steps":             PROBE_STEPS,
    }


# ── Terrain endpoints — 501 until pipeline runs ───────────────────────

def _pipeline_required(name: str):
    return JSONResponse(
        status_code=501,
        content={"detail": f"{name} not yet available. Run the data pipeline first."},
    )

@app.get("/api/concepts")
async def get_concepts():
    return _pipeline_required("concepts")

@app.get("/api/terrain")
async def get_terrain():
    return _pipeline_required("terrain")

@app.get("/api/desert-field")
async def get_desert_field():
    return _pipeline_required("desert-field")

@app.get("/api/basin-data")
async def get_basin_data():
    return _pipeline_required("basin-data")

@app.get("/api/basin-assignments")
async def get_basin_assignments():
    return _pipeline_required("basin-assignments")

@app.get("/api/attractors")
async def get_attractors():
    return _pipeline_required("attractors")

@app.get("/api/voronoi-vertices")
async def get_voronoi_vertices():
    return _pipeline_required("voronoi-vertices")

@app.get("/api/dig-sites")
async def get_dig_sites():
    return _pipeline_required("dig-sites")

@app.get("/api/taxonomy")
async def get_taxonomy():
    return _pipeline_required("taxonomy")

@app.post("/api/probe")
async def probe():
    return _pipeline_required("probe")


# ── Generative decoding ───────────────────────────────────────────────

@app.post("/api/describe-point")
async def describe_point(request: Request):
    """
    Describe a point in embedding space using the LLM.
    - Rate-limited at backend (not frontend) level
    - API key never in client code
    - LLM response HTML-entity-encoded before returning
    - Only called when desert_value >= DESERT_GATE_THRESHOLD
    """
    global _last_llm_call

    from .config import (
        ANTHROPIC_API_KEY, DESERT_GATE_THRESHOLD, DESERT_SHALLOW_THRESHOLD,
        LLM_MODEL, LLM_MAX_TOKENS, MAX_QUERY_LENGTH,
    )

    # Backend rate limiting
    elapsed = time.time() - _last_llm_call
    if elapsed < LLM_RATE_LIMIT_INTERVAL_SECONDS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limited. Try again shortly."},
        )

    if not ANTHROPIC_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"detail": "LLM API key not configured."},
        )

    body = await request.json()

    desert_value = float(body.get("desert_value", 0.0))
    if desert_value < DESERT_GATE_THRESHOLD:
        return JSONResponse(
            status_code=422,
            content={"detail": "Desert value below gate threshold. No description generated."},
        )

    nearest = body.get("nearest_concepts", [])
    if not isinstance(nearest, list) or len(nearest) == 0:
        return JSONResponse(
            status_code=422,
            content={"detail": "nearest_concepts required."},
        )

    def sanitize(s: str) -> str:
        s = re.sub(r'[\x00-\x1f\x7f]', '', str(s))
        return s[:MAX_QUERY_LENGTH]

    roget_ctx = body.get("roget_context") or {}
    cat_a     = sanitize(roget_ctx.get("category_a", "unknown"))
    cat_b     = sanitize(roget_ctx.get("category_b", "unknown"))
    class_a   = sanitize(roget_ctx.get("class_a", ""))
    section_a = sanitize(roget_ctx.get("section_a", ""))
    class_b   = sanitize(roget_ctx.get("class_b", ""))
    section_b = sanitize(roget_ctx.get("section_b", ""))

    concept_lines = "\n".join(
        f"  {sanitize(c.get('term','?'))} "
        f"(distance: {float(c.get('distance', 0)):.4f}, "
        f"category: {sanitize(c.get('roget_category_name', c.get('domain','unknown')))})"
        for c in nearest[:5]
    )

    prefix = (
        "[Shallow desert] "
        if desert_value < DESERT_SHALLOW_THRESHOLD
        else ""
    )

    user_prompt = (
        f"This point in embedding space lies between {cat_a} ({class_a}: {section_a}) "
        f"and {cat_b} ({class_b}: {section_b}).\n"
        f"The nearest named concepts are:\n{concept_lines}\n"
        f"Desert distance: {desert_value:.4f}\n"
        f"Describe what meaning might live here."
    )

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    _last_llm_call = time.time()

    try:
        message = client.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=(
                "You are describing unnamed concepts found in the gaps between "
                "conceptual categories. Be concrete, specific, and terse. "
                "1–2 sentences maximum. Do not be abstract or vague. "
                "Describe what the concept IS, not what it is like."
            ),
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text if message.content else ""
        # HTML-entity-encode — frontend must not render this as raw HTML
        description = prefix + html.escape(raw)
        return {"description": description, "desert_value": desert_value}
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"detail": f"LLM call failed: {str(e)[:200]}"},
        )
