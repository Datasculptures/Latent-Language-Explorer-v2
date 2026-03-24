"""
find_dig_sites.py
Enumerate lexical desert regions from the precomputed desert field.

Thresholds the 2D desert field at DESERT_DIG_SITE_THRESHOLD, finds
connected components (4-connected), filters small regions, and ranks
by mean desert value.

Output: backend/data/dig_sites.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.ndimage import label

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESERT_NPZ   = PROJECT_ROOT / "data" / "terrain" / "desert_field.npz"
OUTPUT_JSON  = PROJECT_ROOT / "backend" / "data" / "dig_sites.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import DESERT_DIG_SITE_THRESHOLD, DESERT_DIG_SITE_MIN_CELLS


def main():
    if not DESERT_NPZ.exists():
        print(f"ERROR: {DESERT_NPZ} not found.")
        sys.exit(1)

    data   = np.load(DESERT_NPZ, allow_pickle=True)
    desert = data["desert"]   # (128, 128) normalized [0,1]
    x_grid = data["x_grid"]
    y_grid = data["y_grid"]

    print(f"Desert field: {desert.shape}")
    print(f"Threshold:    {DESERT_DIG_SITE_THRESHOLD}")

    # Binary mask of deep desert regions
    mask            = desert >= DESERT_DIG_SITE_THRESHOLD
    labeled, n_comp = label(mask)  # 4-connected components
    print(f"Connected components above threshold: {n_comp}")

    sites = []
    for comp_id in range(1, n_comp + 1):
        comp_mask  = labeled == comp_id
        cell_count = int(comp_mask.sum())
        if cell_count < DESERT_DIG_SITE_MIN_CELLS:
            continue

        rows, cols  = np.where(comp_mask)
        mean_desert = float(desert[comp_mask].mean())
        max_desert  = float(desert[comp_mask].max())

        # Centroid in grid indices
        cy = float(rows.mean())
        cx = float(cols.mean())

        # Convert to UMAP coordinates
        cx_idx = min(int(round(cx)), len(x_grid) - 1)
        cy_idx = min(int(round(cy)), len(y_grid) - 1)
        umap_x = float(x_grid[cx_idx])
        umap_y = float(y_grid[cy_idx])

        # Bounding box in UMAP coordinates
        bbox = {
            "x_min": float(x_grid[min(cols)]),
            "x_max": float(x_grid[min(max(cols), len(x_grid) - 1)]),
            "y_min": float(y_grid[min(rows)]),
            "y_max": float(y_grid[min(max(rows), len(y_grid) - 1)]),
        }

        sites.append({
            "id":          f"dig_{comp_id:04d}",
            "centroid_x":  umap_x,
            "centroid_y":  umap_y,
            "mean_desert": mean_desert,
            "max_desert":  max_desert,
            "cell_count":  cell_count,
            "bbox":        bbox,
        })

    # Sort by mean desert descending
    sites.sort(key=lambda s: s["mean_desert"], reverse=True)

    # Assign rank
    for i, s in enumerate(sites):
        s["rank"] = i + 1

    result = {
        "meta": {
            "threshold":   DESERT_DIG_SITE_THRESHOLD,
            "min_cells":   DESERT_DIG_SITE_MIN_CELLS,
            "total_sites": len(sites),
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        },
        "sites": sites,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nDig sites found: {len(sites)}")
    if sites:
        print(f"  Deepest:  rank 1, mean_desert={sites[0]['mean_desert']:.4f}, "
              f"cells={sites[0]['cell_count']}")
    print(f"Wrote: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
