"""
compute_basins.py
Compute basin boundary lines from the attractor assignments.

Each grid cell belongs to one attractor's basin (from compute_attractors.py).
Basin boundaries are edges between adjacent cells with different basin IDs.

Output: data/terrain/basin_boundaries.json
  - boundaries: list of line segments [(x1,y1,x2,y2)] in UMAP coordinates
  - basin_grid: (128, 128) array of basin IDs as a flat list (for frontend)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
DENSITY_NPZ     = PROJECT_ROOT / "data" / "terrain" / "density_field.npz"
ATTRACTORS_JSON = PROJECT_ROOT / "data" / "terrain" / "attractors.json"
TERRAIN_DIR     = PROJECT_ROOT / "data" / "terrain"
OUTPUT_JSON     = TERRAIN_DIR / "basin_boundaries.json"


def main():
    for f in [DENSITY_NPZ, ATTRACTORS_JSON]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    d_data = np.load(DENSITY_NPZ, allow_pickle=True)
    x_grid = d_data["x_grid"]
    y_grid = d_data["y_grid"]
    res    = len(x_grid)

    with open(ATTRACTORS_JSON) as f:
        attr_data = json.load(f)

    # Reconstruct basin grid from attractor positions
    # Each cell's basin ID = its canonical attractor ID string
    # Unassigned cells filled via nearest-neighbour
    print("Reconstructing basin grid ...")
    basin_grid    = np.full((res, res), "", dtype=object)
    assigned_mask = np.zeros((res, res), dtype=bool)

    for attr in attr_data["attractors"]:
        r, c = attr["grid_row"], attr["grid_col"]
        if 0 <= r < res and 0 <= c < res:
            basin_grid[r, c]    = attr["id"]
            assigned_mask[r, c] = True

    # Fill unassigned cells via nearest-neighbour distance transform
    from scipy.ndimage import distance_transform_edt
    unassigned = ~assigned_mask
    if unassigned.any():
        _, nearest_idx = distance_transform_edt(unassigned, return_indices=True)
        for r in range(res):
            for c in range(res):
                if not assigned_mask[r, c]:
                    nr = nearest_idx[0, r, c]
                    nc = nearest_idx[1, r, c]
                    basin_grid[r, c] = basin_grid[nr, nc]

    # -- Extract boundary segments ------------------------------------------
    print("Extracting basin boundaries ...")
    boundaries = []
    dx = float(x_grid[1] - x_grid[0]) if len(x_grid) > 1 else 1.0
    dy = float(y_grid[1] - y_grid[0]) if len(y_grid) > 1 else 1.0

    for r in range(res):
        for c in range(res):
            # Horizontal boundary (between row r and r+1)
            if r + 1 < res and basin_grid[r, c] != basin_grid[r + 1, c]:
                x1 = float(x_grid[c]) - dx / 2
                x2 = float(x_grid[c]) + dx / 2
                y  = float(y_grid[r]) + dy / 2
                boundaries.append([x1, y, x2, y])
            # Vertical boundary (between col c and c+1)
            if c + 1 < res and basin_grid[r, c] != basin_grid[r, c + 1]:
                x  = float(x_grid[c]) + dx / 2
                y1 = float(y_grid[r]) - dy / 2
                y2 = float(y_grid[r]) + dy / 2
                boundaries.append([x, y1, x, y2])

    print(f"Found {len(boundaries):,} boundary segments.")

    result = {
        "meta": {
            "boundary_count":  len(boundaries),
            "grid_resolution": res,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        },
        "boundaries": boundaries,
        "basin_grid":  basin_grid.tolist(),
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"Wrote: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
