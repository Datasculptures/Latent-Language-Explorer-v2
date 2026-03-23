"""
compute_density.py
Compute KDE density field over the 2D UMAP layout.

The density field becomes the terrain heightfield:
  high density (many nearby concepts) = high terrain
  low density (sparse concepts) = low terrain / valleys

Grid resolution: 128x128 by default (DESERT_FIELD_RESOLUTION from config).
Bandwidth: Scott's rule (scipy default).

Output: data/terrain/density_field.npz
  - density:   float32 (128, 128) -- KDE density values, normalized [0,1]
  - density_raw: float32 (128, 128) -- raw KDE output before normalization
  - x_grid:    float32 (128,) -- x coordinates of grid columns
  - y_grid:    float32 (128,) -- y coordinates of grid rows
  - x_range:   [min, max] of UMAP x positions (with 5% margin)
  - y_range:   [min, max] of UMAP y positions (with 5% margin)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.stats import gaussian_kde

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UMAP_NPZ     = PROJECT_ROOT / "data" / "embeddings" / "umap_positions.npz"
TERRAIN_DIR  = PROJECT_ROOT / "data" / "terrain"
OUTPUT_NPZ   = TERRAIN_DIR / "density_field.npz"
OUTPUT_META  = TERRAIN_DIR / "density_meta.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import DESERT_FIELD_RESOLUTION


def main():
    if not UMAP_NPZ.exists():
        print(f"ERROR: {UMAP_NPZ} not found. Run compute_umap.py first.")
        sys.exit(1)

    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading UMAP positions ...")
    data      = np.load(UMAP_NPZ, allow_pickle=True)
    positions = data["positions"]  # (N, 2)
    terms     = data["terms"]
    N         = len(terms)
    print(f"Loaded: {N:,} terms")

    # Grid extent: UMAP range + 5% margin on each side
    margin  = 0.05
    x_min, x_max = positions[:, 0].min(), positions[:, 0].max()
    y_min, y_max = positions[:, 1].min(), positions[:, 1].max()
    x_pad   = (x_max - x_min) * margin
    y_pad   = (y_max - y_min) * margin
    x_range = [float(x_min - x_pad), float(x_max + x_pad)]
    y_range = [float(y_min - y_pad), float(y_max + y_pad)]

    res     = DESERT_FIELD_RESOLUTION  # 128
    x_grid  = np.linspace(x_range[0], x_range[1], res, dtype=np.float32)
    y_grid  = np.linspace(y_range[0], y_range[1], res, dtype=np.float32)
    xx, yy  = np.meshgrid(x_grid, y_grid)  # each (128, 128)
    grid_pts = np.vstack([xx.ravel(), yy.ravel()])  # (2, 128*128)

    print(f"\nFitting KDE on {N:,} points ...")
    print(f"  Grid resolution: {res}x{res}")
    print(f"  X range: {x_range}")
    print(f"  Y range: {y_range}")

    kde = gaussian_kde(positions.T)  # positions.T is (2, N)
    bw  = float(kde.factor)
    print(f"  Bandwidth (Scott's rule): {bw:.4f}")

    print("  Evaluating KDE on grid (this may take 1-3 minutes) ...")
    density_flat = kde(grid_pts).astype(np.float32)
    density      = density_flat.reshape(res, res)  # (128, 128)

    # Normalize density to [0, 1] for consistent heightfield scaling
    d_min, d_max = density.min(), density.max()
    density_norm = ((density - d_min) / max(d_max - d_min, 1e-8)).astype(np.float32)

    np.savez_compressed(
        OUTPUT_NPZ,
        density=density_norm,
        density_raw=density,
        x_grid=x_grid,
        y_grid=y_grid,
    )

    meta = {
        "grid_resolution":  res,
        "x_range":          x_range,
        "y_range":          y_range,
        "bandwidth":        bw,
        "bandwidth_method": "Scott's rule (scipy default)",
        "density_min_raw":  float(d_min),
        "density_max_raw":  float(d_max),
        "density_note": (
            "density_field.density is normalized to [0,1]. "
            "This is the terrain heightfield: high density = high terrain. "
            "The z-coordinate in Three.js is derived from this field, "
            "NOT from a third UMAP dimension."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_META, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nDensity field complete:")
    print(f"  Shape:   {density_norm.shape}")
    print(f"  Min:     {density_norm.min():.4f}")
    print(f"  Max:     {density_norm.max():.4f}")
    print(f"  Mean:    {density_norm.mean():.4f}")
    print(f"Wrote: {OUTPUT_NPZ}")


if __name__ == "__main__":
    main()
