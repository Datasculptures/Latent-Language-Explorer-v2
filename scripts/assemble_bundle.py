"""
assemble_bundle.py
Assemble all pipeline outputs into the data bundle.

Validates the output against data/schema/data_bundle.schema.json.

Output: backend/data/data_bundle.json  (served by FastAPI to frontend)
        backend/data/terrain_data.json (terrain grids for Three.js)

data_bundle.json: concept metadata + positions + contextual spread
terrain_data.json: density, gradient, desert, basin grids
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
VOCAB_FILE      = PROJECT_ROOT / "data" / "roget" / "vocab_validated.json"
INDEX_FILE      = PROJECT_ROOT / "data" / "roget" / "vocab_index.json"
COLOUR_FILE     = PROJECT_ROOT / "data" / "roget" / "category_colours.json"
UMAP_NPZ        = PROJECT_ROOT / "data" / "embeddings" / "umap_positions.npz"
CTX_NPZ         = PROJECT_ROOT / "data" / "embeddings" / "contextual_embeddings.npz"
CTX_META        = PROJECT_ROOT / "data" / "embeddings" / "contextual_meta.json"
UMAP_META       = PROJECT_ROOT / "data" / "embeddings" / "umap_meta.json"
BASE_NPZ        = PROJECT_ROOT / "data" / "embeddings" / "base_embeddings.npz"
DENSITY_NPZ     = PROJECT_ROOT / "data" / "terrain" / "density_field.npz"
GRADIENT_NPZ    = PROJECT_ROOT / "data" / "terrain" / "gradient_field.npz"
DESERT_NPZ      = PROJECT_ROOT / "data" / "terrain" / "desert_field.npz"
ATTRACTORS_JSON  = PROJECT_ROOT / "data" / "terrain" / "attractors.json"
BASINS_JSON      = PROJECT_ROOT / "data" / "terrain" / "basin_boundaries.json"
SCHEMA_FILE      = PROJECT_ROOT / "data" / "schema" / "data_bundle.schema.json"

BACKEND_DATA      = PROJECT_ROOT / "backend" / "data"
BUNDLE_FILE       = BACKEND_DATA / "data_bundle.json"
TERRAIN_FILE      = BACKEND_DATA / "terrain_data.json"
TORTUOSITY_JSON   = BACKEND_DATA / "tortuosity.json"
CTX_POS_FILE      = BACKEND_DATA / "context_positions.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    UMAP_RANDOM_SEED, DATA_BUNDLE_VERSION, SCHEMA_VERSION,
    ROGET_CLASSES,
)


def get_git_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def main():
    required = [
        VOCAB_FILE, INDEX_FILE, COLOUR_FILE, UMAP_NPZ, CTX_NPZ,
        CTX_META, UMAP_META, BASE_NPZ,
        DENSITY_NPZ, GRADIENT_NPZ, DESERT_NPZ,
        ATTRACTORS_JSON, BASINS_JSON,
    ]
    for f in required:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    print("Loading all pipeline outputs ...")

    with open(VOCAB_FILE) as f:
        vocab = json.load(f)
    with open(INDEX_FILE) as f:
        index = json.load(f)
    with open(COLOUR_FILE) as f:
        colours = json.load(f)

    umap_data = np.load(UMAP_NPZ, allow_pickle=True)
    ctx_data  = np.load(CTX_NPZ,  allow_pickle=True)
    umap_meta = json.load(open(UMAP_META))
    ctx_meta  = json.load(open(CTX_META))

    positions       = umap_data["positions"]    # (N, 2)
    umap_terms      = list(umap_data["terms"])
    ctx_embeddings  = ctx_data["embeddings"]    # (N, 7, 384)
    ctx_terms       = list(ctx_data["terms"])
    spreads         = ctx_data["spreads"]
    polysemy_scores = ctx_data["polysemy_scores"]

    pos_map      = {t: positions[i].tolist() for i, t in enumerate(umap_terms)}
    spread_map   = {t: float(spreads[i]) for i, t in enumerate(ctx_terms)}
    polysemy_map = {t: float(polysemy_scores[i]) for i, t in enumerate(ctx_terms)}
    ctx_keys     = ctx_meta["context_keys"]

    # Contextual variant distances from neutral vector per term
    print("Computing contextual variant distances ...")
    neutral_idx = ctx_keys.index("neutral")
    ctx_variants: dict[str, list] = {}
    for i, term in enumerate(ctx_terms):
        if term not in pos_map:
            continue
        base_pos = pos_map[term]
        term_ctx_pos = ctx_positions.get(term, [])
        variants = []
        for j, key in enumerate(ctx_keys):
            # Use computed position if available, else fall back to base position
            if j < len(term_ctx_pos):
                pos_2d = term_ctx_pos[j]
            else:
                pos_2d = base_pos  # placeholder until compute_context_positions.py runs
            variants.append({
                "roget_class_context": key,
                "position_2d":         pos_2d,
                "distance_from_base":  float(
                    np.linalg.norm(
                        ctx_embeddings[i, j] - ctx_embeddings[i, neutral_idx]
                    )
                ),
            })
        ctx_variants[term] = variants

    # Terrain grids
    d_data  = np.load(DENSITY_NPZ,  allow_pickle=True)
    g_data  = np.load(GRADIENT_NPZ, allow_pickle=True)
    ds_data = np.load(DESERT_NPZ,   allow_pickle=True)
    with open(ATTRACTORS_JSON) as f:
        attractors = json.load(f)
    with open(BASINS_JSON) as f:
        basins = json.load(f)

    # Context positions — optional, produced by compute_context_positions.py
    ctx_positions: dict = {}
    if CTX_POS_FILE.exists():
        with open(CTX_POS_FILE) as f:
            ctx_positions = json.load(f)
        print(f"Loaded context positions for {len(ctx_positions):,} terms.")
    else:
        print("Note: context_positions.json not found — "
              "using base position as placeholder for context variants.")

    # Tortuosity is optional — only added if compute_tortuosity.py has run
    tortuosity_map: dict = {}
    if TORTUOSITY_JSON.exists():
        with open(TORTUOSITY_JSON) as f:
            tortuosity_map = json.load(f)
        print(f"Loaded tortuosity for {len(tortuosity_map):,} terms.")

    # -- Build concept list ------------------------------------------------
    print(f"Building concept list for {len(vocab):,} terms ...")
    concepts = []
    for v in vocab:
        term = v["term"]
        if term not in pos_map:
            continue
        colour = colours.get(f"cat_{v['primary_category_id']}", "#888888")
        concepts.append({
            "id":                   f"t_{term}",
            "label":                term,
            "roget_category_id":    v["primary_category_id"],
            "roget_category_name":  v["primary_category_name"],
            "roget_section_name":   v["primary_section_name"],
            "roget_class_id":       v["primary_class_id"],
            "roget_class_name":     v["primary_class_name"],
            "is_polysemous":        v["is_polysemous"],
            "all_roget_categories": v["all_category_ids"],
            "is_modern_addition":   v["is_modern_addition"],
            "is_obsolete":          v.get("is_obsolete", False),
            "position_2d":          pos_map[term],
            "context_spread":       spread_map.get(term),
            "polysemy_score":       polysemy_map.get(term),
            "colour":               colour,
            "tortuosity":           tortuosity_map.get(term),
            "contexts":             ctx_variants.get(term, []),
        })

    # -- Assemble data bundle ----------------------------------------------
    bundle = {
        "meta": {
            "schema_version":         SCHEMA_VERSION,
            "data_bundle_version":    DATA_BUNDLE_VERSION,
            "umap_random_seed":       UMAP_RANDOM_SEED,
            "embedding_model":        "all-MiniLM-L6-v2",
            "embedding_dim":          384,
            "pca_components":         umap_meta["pca_output_dim"],
            "umap_components":        2,
            "umap_n_components":      2,
            "term_count":             len(concepts),
            "roget_category_count":   len(set(c["roget_category_id"] for c in concepts)),
            "timestamp":              datetime.now(timezone.utc).isoformat(),
            "contextual_mode":        "template",
            "contextual_model":       "all-MiniLM-L6-v2",
            "pipeline_git_hash":      get_git_hash(),
            "pca_variance_explained": umap_meta.get("pca_variance_explained"),
            "roget_classes":          {str(k): v for k, v in ROGET_CLASSES.items()},
        },
        "concepts": concepts,
    }

    # -- Assemble terrain data ---------------------------------------------
    terrain = {
        "meta": {
            "grid_resolution": int(d_data["x_grid"].shape[0]),
            "x_range": [float(d_data["x_grid"][0]), float(d_data["x_grid"][-1])],
            "y_range": [float(d_data["y_grid"][0]), float(d_data["y_grid"][-1])],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "x_grid":           d_data["x_grid"].tolist(),
        "y_grid":           d_data["y_grid"].tolist(),
        "density":          d_data["density"].tolist(),
        "grad_x":           g_data["grad_x"].tolist(),
        "grad_y":           g_data["grad_y"].tolist(),
        "desert":           ds_data["desert"].tolist(),
        "attractors":       attractors["attractors"],
        "basin_boundaries": basins["boundaries"],
        "basin_grid":       basins["basin_grid"],
    }

    # -- Validate against schema -------------------------------------------
    try:
        import jsonschema
        schema = json.load(open(SCHEMA_FILE))
        sample = {**bundle, "concepts": bundle["concepts"][:100]}
        jsonschema.validate(sample, schema)
        print("Schema validation: OK (sampled first 100 concepts)")
    except ImportError:
        print("WARNING: jsonschema not installed -- skipping schema validation.")
        print("Run: pip install jsonschema")
    except Exception as e:
        print(f"ERROR: Schema validation failed: {e}")
        sys.exit(1)

    # -- Write outputs -----------------------------------------------------
    BACKEND_DATA.mkdir(parents=True, exist_ok=True)
    with open(BUNDLE_FILE, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False)
    print(f"Wrote: {BUNDLE_FILE} ({BUNDLE_FILE.stat().st_size / 1e6:.1f} MB)")

    with open(TERRAIN_FILE, "w", encoding="utf-8") as f:
        json.dump(terrain, f, ensure_ascii=False)
    print(f"Wrote: {TERRAIN_FILE} ({TERRAIN_FILE.stat().st_size / 1e6:.1f} MB)")

    print(f"\nData bundle summary:")
    print(f"  Concepts:    {len(concepts):,}")
    print(f"  Categories:  {bundle['meta']['roget_category_count']:,}")
    print(f"  UMAP seed:   {UMAP_RANDOM_SEED} (must be 42)")
    print(f"  Git hash:    {bundle['meta']['pipeline_git_hash']}")
    print(f"\nPhase 2 complete. Backend can now serve terrain data.")
    print(f"Proceed to Phase 3: discovery pipeline.")


if __name__ == "__main__":
    main()
