"""
compute_desert_field.py
Compute the lexical desert distance field.

For each point on the 128x128 grid in 2D UMAP space:
  distance = Euclidean distance (in UMAP 2D space) to the nearest
             vocabulary term's UMAP position.

This grid is used for:
  - Terrain visualization (desert surface mode)
  - Dig site enumeration (find deepest desert pockets)
  - Threshold-based region highlighting

Note: Probe desert distances are computed separately in high-D space.
This script computes the 2D grid version for visualization.

Output: data/terrain/desert_field.npz
  - desert:      float32 (128, 128) -- normalized [0,1] desert distances
  - desert_raw:  float32 (128, 128) -- raw 2D UMAP distances
  - x_grid, y_grid: coordinates matching density_field.npz
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UMAP_NPZ     = PROJECT_ROOT / "data" / "embeddings" / "umap_positions.npz"
DENSITY_NPZ  = PROJECT_ROOT / "data" / "terrain" / "density_field.npz"
TERRAIN_DIR  = PROJECT_ROOT / "data" / "terrain"
OUTPUT_NPZ   = TERRAIN_DIR / "desert_field.npz"
OUTPUT_META  = TERRAIN_DIR / "desert_meta.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    DESERT_FIELD_RESOLUTION, DESERT_FIELD_MAX_RESOLUTION,
    DESERT_DIG_SITE_THRESHOLD, DESERT_DIG_SITE_MIN_CELLS,
)


def main():
    for f in [UMAP_NPZ, DENSITY_NPZ]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    print("Loading UMAP positions ...")
    u_data    = np.load(UMAP_NPZ, allow_pickle=True)
    positions = u_data["positions"]  # (N, 2)
    terms     = u_data["terms"]
    N         = len(terms)
    print(f"Loaded: {N:,} concept positions")

    print("Loading grid definition from density field ...")
    d_data = np.load(DENSITY_NPZ, allow_pickle=True)
    x_grid = d_data["x_grid"]   # (128,)
    y_grid = d_data["y_grid"]   # (128,)
    res    = len(x_grid)

    # Validate grid dimensions
    if res > DESERT_FIELD_MAX_RESOLUTION:
        print(f"ERROR: Grid resolution {res} exceeds maximum {DESERT_FIELD_MAX_RESOLUTION}.")
        sys.exit(1)

    # Build grid point array
    xx, yy   = np.meshgrid(x_grid, y_grid)        # both (128, 128)
    grid_pts = np.column_stack([xx.ravel(), yy.ravel()])  # (16384, 2)

    # Build KD-tree from concept positions for fast nearest-neighbour
    print(f"Building KD-tree from {N:,} concept positions ...")
    tree = cKDTree(positions)

    # Query nearest concept for every grid point
    print(f"Computing desert distances for {res}x{res} = {res*res:,} grid points ...")
    distances, _ = tree.query(grid_pts, k=1, workers=-1)  # parallel
    desert_raw   = distances.reshape(res, res).astype(np.float32)

    # Normalize to [0, 1]
    d_min, d_max = desert_raw.min(), desert_raw.max()
    desert_norm  = ((desert_raw - d_min) / max(d_max - d_min, 1e-8)).astype(np.float32)

    # Count dig site cells (deep deserts above threshold)
    dig_cells = int((desert_norm >= DESERT_DIG_SITE_THRESHOLD).sum())

    np.savez_compressed(
        OUTPUT_NPZ,
        desert=desert_norm,
        desert_raw=desert_raw,
        x_grid=x_grid,
        y_grid=y_grid,
    )

    meta = {
        "grid_resolution":       res,
        "term_count":            int(N),
        "desert_min_raw":        float(d_min),
        "desert_max_raw":        float(d_max),
        "dig_site_threshold":    DESERT_DIG_SITE_THRESHOLD,
        "cells_above_threshold": dig_cells,
        "measurement_space":     "2D UMAP layout space",
        "measurement_note": (
            "desert distances are measured in 2D UMAP space between "
            "grid points and concept positions. Probe desert distances "
            "are measured separately in full high-D embedding space. "
            "These are different measurements."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_META, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nDesert field complete:")
    print(f"  Shape:          {desert_norm.shape}")
    print(f"  Raw max dist:   {d_max:.4f} (UMAP units)")
    print(f"  Dig site cells: {dig_cells:,} (normalized >= {DESERT_DIG_SITE_THRESHOLD})")
    print(f"Wrote: {OUTPUT_NPZ}")


if __name__ == "__main__":
    main()
