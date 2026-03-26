"""
backend/app/main.py
FastAPI application entry point.
Terrain endpoints serve pre-computed pipeline data from backend/data/.
"""
import html
import json as _json
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import (
    PROJECT_VERSION, CORS_ORIGINS,
    LLM_RATE_LIMIT_INTERVAL_SECONDS,
)
from .routers import journal as journal_router
from .routers import fabrication as fabrication_router
from .services import probe_service


@asynccontextmanager
async def lifespan(app_instance):
    # Startup: build embedding index if embeddings are available
    built = probe_service.build_index()
    if built:
        print("Embedding index built and ready.")
    else:
        print("WARNING: Embeddings not found. Probe endpoint will return 501.")
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="Latent Language Explorer V2",
    version=PROJECT_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)

app.include_router(journal_router.router)
app.include_router(fabrication_router.router)

# In-memory rate limiting state (per process)
_last_llm_call: float = 0.0

# ── Data loader ───────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "backend" / "data"


def _load_json(filename: str):
    path = _DATA_DIR / filename
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return _json.load(f)


# ── Health & config ───────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": PROJECT_VERSION}


@app.get("/api/config")
async def get_config():
    """Return non-sensitive configuration values for the frontend."""
    from .config import (
        PROBE_DESERT_GATE_THRESHOLD, PROBE_DESERT_SHALLOW_THRESHOLD,
        LLM_RATE_LIMIT_PER_HOUR, PROBE_STEPS,
    )
    return {
        "desert_gate_threshold":   PROBE_DESERT_GATE_THRESHOLD,
        "desert_shallow_threshold": PROBE_DESERT_SHALLOW_THRESHOLD,
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
    data = _load_json("data_bundle.json")
    if data is None:
        return _pipeline_required("concepts")
    return {"concepts": data["concepts"], "meta": data["meta"]}

@app.get("/api/terrain")
async def get_terrain():
    data = _load_json("terrain_data.json")
    if data is None:
        return _pipeline_required("terrain")
    return data

@app.get("/api/desert-field")
async def get_desert_field():
    data = _load_json("terrain_data.json")
    if data is None:
        return _pipeline_required("desert-field")
    return {
        "desert": data["desert"],
        "x_grid": data["x_grid"],
        "y_grid": data["y_grid"],
        "meta":   data["meta"],
    }

@app.get("/api/attractors")
async def get_attractors():
    data = _load_json("terrain_data.json")
    if data is None:
        return _pipeline_required("attractors")
    return {"attractors": data["attractors"]}

@app.get("/api/basin-data")
async def get_basin_data():
    data = _load_json("terrain_data.json")
    if data is None:
        return _pipeline_required("basin-data")
    return {
        "boundaries": data["basin_boundaries"],
        "basin_grid": data["basin_grid"],
        "meta":       data["meta"],
    }

@app.get("/api/basin-assignments")
async def get_basin_assignments():
    return _pipeline_required("basin-assignments")

@app.get("/api/voronoi-vertices")
async def get_voronoi_vertices():
    data = _load_json("voronoi_data.json")
    if data is None:
        return _pipeline_required("voronoi-vertices")
    return data

@app.get("/api/tortuosity")
async def get_tortuosity():
    data = _load_json("tortuosity.json")
    if data is None:
        return _pipeline_required("tortuosity (run compute_tortuosity.py then assemble_bundle.py)")
    return data

@app.get("/api/dig-sites")
async def get_dig_sites():
    data = _load_json("dig_sites.json")
    if data is None:
        return _pipeline_required("dig-sites")
    return data

@app.get("/api/context-positions")
async def get_context_positions():
    data = _load_json("context_positions.json")
    if data is None:
        return _pipeline_required(
            "context-positions (run scripts/compute_context_positions.py)"
        )
    return data

@app.get("/api/taxonomy")
async def get_taxonomy():
    return _pipeline_required("taxonomy")


# ── Concept graph cache ────────────────────────────────────────────────
_concept_graph: dict | None = None

def _get_concept_graph() -> dict | None:
    global _concept_graph
    if _concept_graph is None:
        _concept_graph = _load_json("concept_graph.json")
    return _concept_graph


@app.post("/api/path")
async def find_path(request: Request):
    """Dijkstra shortest path between two concepts on the k-NN UMAP graph."""
    import heapq
    from .config import MAX_QUERY_LENGTH

    body = await request.json()
    term_a = re.sub(r'[\x00-\x1f\x7f]', '', str(body.get("term_a", ""))).strip()[:MAX_QUERY_LENGTH]
    term_b = re.sub(r'[\x00-\x1f\x7f]', '', str(body.get("term_b", ""))).strip()[:MAX_QUERY_LENGTH]

    if not term_a or not term_b:
        return JSONResponse(status_code=422, content={"detail": "term_a and term_b are required."})

    graph = _get_concept_graph()
    if graph is None:
        return _pipeline_required("path (concept_graph.json not found — run compute_concept_graph.py)")

    terms     = graph["terms"]
    positions = graph["positions"]
    adj       = graph["adj"]

    term_index = {t: i for i, t in enumerate(terms)}

    if term_a not in term_index:
        return JSONResponse(status_code=404, content={"detail": f"Term not found: '{term_a}'"})
    if term_b not in term_index:
        return JSONResponse(status_code=404, content={"detail": f"Term not found: '{term_b}'"})

    src = term_index[term_a]
    dst = term_index[term_b]

    # Dijkstra
    INF  = float("inf")
    dist = [INF] * len(terms)
    prev = [-1]  * len(terms)
    dist[src] = 0.0
    heap = [(0.0, src)]

    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        if u == dst:
            break
        row = adj[u]
        for k in range(0, len(row), 2):
            v  = row[k]
            w  = row[k + 1]
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if dist[dst] == INF:
        return JSONResponse(status_code=404, content={"detail": f"No path found between '{term_a}' and '{term_b}'"})

    # Reconstruct path
    path = []
    cur  = dst
    while cur != -1:
        path.append(cur)
        cur = prev[cur]
    path.reverse()

    steps = [
        {"term": terms[i], "position_2d": positions[i]}
        for i in path
    ]

    return {
        "term_a":       term_a,
        "term_b":       term_b,
        "steps":        steps,
        "total_length": round(dist[dst], 6),
        "step_count":   len(steps),
    }

@app.post("/api/probe")
async def probe_endpoint(request: Request):
    from .config import MAX_QUERY_LENGTH, PROBE_STEPS

    body = await request.json()

    def sanitize_term(s: str) -> str:
        s = re.sub(r'[\x00-\x1f\x7f]', '', str(s))
        return s.strip()[:MAX_QUERY_LENGTH]

    term_a  = sanitize_term(body.get("term_a", ""))
    term_b  = sanitize_term(body.get("term_b", ""))
    n_steps = int(body.get("n_steps", PROBE_STEPS))
    n_steps = max(2, min(n_steps, 100))  # clamp

    if not term_a or not term_b:
        return JSONResponse(
            status_code=422,
            content={"detail": "term_a and term_b are required."},
        )

    idx = probe_service.get_index()
    if idx is None or not idx.built:
        return _pipeline_required("probe (embeddings not loaded)")

    result = probe_service.probe(term_a, term_b, n_steps=n_steps)
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"One or both terms not found in index: "
                                f"'{term_a}', '{term_b}'"},
        )
    return result


@app.get("/api/nearest")
async def get_nearest(term: str, k: int = 10):
    """Return k nearest concepts to a given term in high-D space."""
    from .config import MAX_QUERY_LENGTH
    term = re.sub(r'[\x00-\x1f\x7f]', '', term).strip()[:MAX_QUERY_LENGTH]
    k    = max(1, min(k, 50))

    idx = probe_service.get_index()
    if idx is None or not idx.built:
        return _pipeline_required("nearest (embeddings not loaded)")

    vec = idx.get_embedding(term)
    if vec is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Term not found: '{term}'"},
        )
    nearest = idx.nearest_k(vec, k=k, exclude_terms={term})
    return {"term": term, "nearest": nearest}


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
        PROBE_DESERT_GATE_THRESHOLD    as DESERT_GATE_THRESHOLD,
        PROBE_DESERT_SHALLOW_THRESHOLD as DESERT_SHALLOW_THRESHOLD,
        LLM_MODEL, LLM_MAX_TOKENS, MAX_QUERY_LENGTH,
        PROJECT_ROOT,
    )

    # Read API key fresh each call so .env changes take effect without restart
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    if not ANTHROPIC_API_KEY:
        _env = PROJECT_ROOT / ".env"
        if _env.exists():
            with open(_env, encoding="utf-8") as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line.startswith("ANTHROPIC_API_KEY="):
                        ANTHROPIC_API_KEY = _line.split("=", 1)[1].strip().strip("\"'")
                        break

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
