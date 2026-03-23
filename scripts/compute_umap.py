"""
compute_umap.py
PCA reduction (384d -> 256d) followed by UMAP projection (256d -> 2d).

UMAP_RANDOM_SEED is read from terrain_config.py.
The seed must be 42. This script refuses to run with any other value
to prevent accidental terrain invalidation.

The output is a 2D layout. Terrain height is derived in a later step
from KDE density -- it is NOT a UMAP dimension.

Output: data/embeddings/umap_positions.npz
  - terms:     string array (N,) -- same order as base_embeddings
  - positions: float32 array (N, 2) -- 2D UMAP layout positions

Also writes: data/embeddings/umap_meta.json
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_NPZ     = PROJECT_ROOT / "data" / "embeddings" / "base_embeddings.npz"
EMBED_DIR    = PROJECT_ROOT / "data" / "embeddings"
OUTPUT_NPZ   = EMBED_DIR / "umap_positions.npz"
OUTPUT_META  = EMBED_DIR / "umap_meta.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    UMAP_RANDOM_SEED, UMAP_N_COMPONENTS, UMAP_N_NEIGHBORS, UMAP_MIN_DIST,
    PCA_N_COMPONENTS,
)

# Seed guard -- refuse to run if seed has been changed
if UMAP_RANDOM_SEED != 42:
    print(f"ERROR: UMAP_RANDOM_SEED is {UMAP_RANDOM_SEED}, expected 42.")
    print("Changing the seed invalidates all journal coordinates.")
    print("If this change is intentional, increment SCHEMA_VERSION in terrain_config.py")
    print("and write a coordinate migration script before proceeding.")
    sys.exit(1)

if UMAP_N_COMPONENTS != 2:
    print(f"ERROR: UMAP_N_COMPONENTS is {UMAP_N_COMPONENTS}, must be 2.")
    print("The terrain height is KDE density, not a UMAP dimension.")
    sys.exit(1)


def main():
    if not BASE_NPZ.exists():
        print(f"ERROR: {BASE_NPZ} not found. Run compute_base_embeddings.py first.")
        sys.exit(1)

    try:
        from sklearn.decomposition import PCA
        import umap
    except ImportError:
        print("ERROR: sklearn or umap-learn not installed.")
        print("Run: pip install scikit-learn umap-learn")
        sys.exit(1)

    print("Loading base embeddings ...")
    data       = np.load(BASE_NPZ, allow_pickle=True)
    terms      = list(data["terms"])
    embeddings = data["embeddings"].astype(np.float32)
    N, D       = embeddings.shape
    print(f"Loaded: {N:,} terms x {D} dimensions")

    # -- PCA: 384d -> 256d ---------------------------------------------------
    print(f"\nRunning PCA: {D}d -> {PCA_N_COMPONENTS}d ...")
    t0  = time.time()
    pca = PCA(n_components=PCA_N_COMPONENTS, random_state=UMAP_RANDOM_SEED)
    embeddings_pca     = pca.fit_transform(embeddings).astype(np.float32)
    variance_explained = float(pca.explained_variance_ratio_.sum())
    print(f"  PCA complete in {time.time()-t0:.1f}s")
    print(f"  Variance explained: {100*variance_explained:.1f}%")
    print(f"  Output shape: {embeddings_pca.shape}")

    # -- UMAP: 256d -> 2d ----------------------------------------------------
    print(f"\nRunning UMAP: {PCA_N_COMPONENTS}d -> {UMAP_N_COMPONENTS}d ...")
    print(f"  Seed:        {UMAP_RANDOM_SEED} (canonical -- do not change)")
    print(f"  N_neighbors: {UMAP_N_NEIGHBORS}")
    print(f"  Min_dist:    {UMAP_MIN_DIST}")
    print(f"  n_terms:     {N:,}")
    print(f"  This may take 5-20 minutes for 36,000+ terms on CPU.")
    t0 = time.time()

    reducer = umap.UMAP(
        n_components=UMAP_N_COMPONENTS,
        n_neighbors=UMAP_N_NEIGHBORS,
        min_dist=UMAP_MIN_DIST,
        random_state=UMAP_RANDOM_SEED,
        verbose=True,
        low_memory=False,
    )
    positions_2d = reducer.fit_transform(embeddings_pca).astype(np.float32)
    elapsed      = time.time() - t0
    print(f"\n  UMAP complete in {elapsed/60:.1f} minutes")
    print(f"  Output shape: {positions_2d.shape}")
    print(f"  X range: [{positions_2d[:,0].min():.3f}, {positions_2d[:,0].max():.3f}]")
    print(f"  Y range: [{positions_2d[:,1].min():.3f}, {positions_2d[:,1].max():.3f}]")

    # -- Write output --------------------------------------------------------
    np.savez_compressed(
        OUTPUT_NPZ,
        terms=terms,
        positions=positions_2d,
    )

    meta = {
        "umap_random_seed":       UMAP_RANDOM_SEED,
        "umap_n_components":      UMAP_N_COMPONENTS,
        "umap_n_neighbors":       UMAP_N_NEIGHBORS,
        "umap_min_dist":          UMAP_MIN_DIST,
        "pca_input_dim":          D,
        "pca_output_dim":         PCA_N_COMPONENTS,
        "pca_variance_explained": variance_explained,
        "term_count":             N,
        "position_dim":           UMAP_N_COMPONENTS,
        "position_note": (
            "positions are 2D UMAP layout coordinates [x, y]. "
            "Terrain height (z in 3D scene) is derived from KDE density "
            "in a separate step -- it is NOT a UMAP dimension."
        ),
        "elapsed_seconds":  elapsed,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_META, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nWrote: {OUTPUT_NPZ}")
    print(f"Wrote: {OUTPUT_META}")

    # Sanity check: nearby terms in UMAP should be semantically related
    print(f"\nSanity check -- nearest neighbours in UMAP 2D space:")
    check_terms = ["existence", "motion", "light", "knowledge", "beauty"]
    pos_map = {t: positions_2d[i] for i, t in enumerate(terms)}
    for check in check_terms:
        if check not in pos_map:
            continue
        p     = pos_map[check]
        dists = {t: np.linalg.norm(positions_2d[i] - p)
                 for i, t in enumerate(terms) if t != check}
        nearest = sorted(dists.items(), key=lambda x: x[1])[:5]
        print(f"  '{check}' nearest: {[n[0] for n in nearest]}")


if __name__ == "__main__":
    main()
