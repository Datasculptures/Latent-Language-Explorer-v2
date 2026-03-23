"""
compute_gradients.py
Compute the gradient field of the density heightfield.

The gradient at each grid point gives the direction of steepest ascent
in density. Used for gradient ascent to find attractor peaks.

Output: data/terrain/gradient_field.npz
  - grad_x:    float32 (128, 128) -- gradient in x direction
  - grad_y:    float32 (128, 128) -- gradient in y direction
  - magnitude: float32 (128, 128) -- gradient magnitude
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DENSITY_NPZ  = PROJECT_ROOT / "data" / "terrain" / "density_field.npz"
TERRAIN_DIR  = PROJECT_ROOT / "data" / "terrain"
OUTPUT_NPZ   = TERRAIN_DIR / "gradient_field.npz"
OUTPUT_META  = TERRAIN_DIR / "gradient_meta.json"


def main():
    if not DENSITY_NPZ.exists():
        print(f"ERROR: {DENSITY_NPZ} not found. Run compute_density.py first.")
        sys.exit(1)

    print("Loading density field ...")
    data    = np.load(DENSITY_NPZ, allow_pickle=True)
    density = data["density"]   # (128, 128), normalized [0,1]
    x_grid  = data["x_grid"]
    y_grid  = data["y_grid"]

    # Grid spacing
    dx = float(x_grid[1] - x_grid[0]) if len(x_grid) > 1 else 1.0
    dy = float(y_grid[1] - y_grid[0]) if len(y_grid) > 1 else 1.0

    print(f"Grid: {density.shape}, dx={dx:.4f}, dy={dy:.4f}")

    # Gradient: numpy.gradient uses central differences (2nd order accurate)
    # Note: density is indexed [row, col] = [y, x]
    # np.gradient returns (grad_along_axis0, grad_along_axis1) = (grad_y, grad_x)
    grad_y, grad_x = np.gradient(density, dy, dx)
    grad_x    = grad_x.astype(np.float32)
    grad_y    = grad_y.astype(np.float32)
    magnitude = np.sqrt(grad_x**2 + grad_y**2).astype(np.float32)

    np.savez_compressed(OUTPUT_NPZ, grad_x=grad_x, grad_y=grad_y, magnitude=magnitude)

    meta = {
        "grid_shape":      list(density.shape),
        "dx":              dx,
        "dy":              dy,
        "grad_mag_mean":   float(magnitude.mean()),
        "grad_mag_max":    float(magnitude.max()),
        "method":          "numpy.gradient (central differences, 2nd order)",
        "timestamp":       datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_META, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nGradient field complete:")
    print(f"  grad_x shape:   {grad_x.shape}")
    print(f"  Magnitude mean: {magnitude.mean():.4f}, max: {magnitude.max():.4f}")
    print(f"Wrote: {OUTPUT_NPZ}")


if __name__ == "__main__":
    main()
