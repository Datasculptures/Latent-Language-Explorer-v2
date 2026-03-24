"""
export_stl.py
Export a terrain patch as an STL mesh.

Outputs: backend/data/exports/{title}_{timestamp}.stl

The mesh is a triangulated heightfield:
  - X, Y dimensions correspond to physical base dimensions
  - Z (height) is scaled by max_height
  - One triangle per grid cell, two triangles per square

This is a reference for manual layered construction, not for
direct 3D printing. The mesh is a surface only (open bottom).

Usage:
  py scripts/export_stl.py \
     [--title "discovery_name"] \
     [--grid-size 48] \
     [--base-size 12.0] \
     [--max-height 6.0] \
     [--focus-x FLOAT --focus-y FLOAT --focus-radius FLOAT] \
     [--output-dir backend/data/exports/]
"""

import re
import struct
import sys
from datetime import datetime
from pathlib import Path
import json
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERRAIN_FILE = PROJECT_ROOT / "backend" / "data" / "terrain_data.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    EXPORT_DEFAULT_GRID_SIZE, EXPORT_DEFAULT_BASE_INCHES,
    EXPORT_DEFAULT_MAX_HEIGHT_INCHES, EXPORT_CONTOUR_INTERVAL_INCHES,
    EXPORT_MAX_GRID_DIMENSION,
)


def safe_output_dir(path_str: str) -> Path:
    exports_root = (PROJECT_ROOT / "backend" / "data" / "exports").resolve()
    resolved     = Path(path_str).resolve()
    if not str(resolved).startswith(str(exports_root)):
        raise ValueError(f"Output path must be within {exports_root}.")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def sanitize_title(title: str) -> str:
    title = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', '', title)
    return title.strip()[:80] or "terrain"


def build_heightfield(
    density,
    x_grid,
    y_grid,
    grid_size:  int,
    base_size:  float,
    max_height: float,
    focus_x,
    focus_y,
    focus_radius,
):
    """
    Sample density onto a fabrication grid and scale to physical units.
    Returns (elev, xs, ys, cell_x, cell_y).
    elev is float32 array (grid_size, grid_size) in inches.
    """
    density_arr = np.array(density, dtype=np.float32)
    xg, yg      = np.array(x_grid), np.array(y_grid)

    if focus_x is not None:
        x_min, x_max = focus_x - focus_radius, focus_x + focus_radius
        y_min, y_max = focus_y - focus_radius, focus_y + focus_radius
    else:
        x_min, x_max = float(xg[0]), float(xg[-1])
        y_min, y_max = float(yg[0]), float(yg[-1])

    xs = np.linspace(x_min, x_max, grid_size)
    ys = np.linspace(y_min, y_max, grid_size)

    cell_x = base_size / (grid_size - 1)
    cell_y = base_size / (grid_size - 1)

    elev = np.zeros((grid_size, grid_size), dtype=np.float32)
    for ri, uy in enumerate(ys):
        for ci, ux in enumerate(xs):
            xi = max(0, min(int(np.searchsorted(xg, ux)) - 1, len(xg) - 2))
            yi = max(0, min(int(np.searchsorted(yg, uy)) - 1, len(yg) - 2))
            tx = float(np.clip((ux - xg[xi]) / (xg[xi+1] - xg[xi] + 1e-8), 0, 1))
            ty = float(np.clip((uy - yg[yi]) / (yg[yi+1] - yg[yi] + 1e-8), 0, 1))
            v  = (density_arr[yi,   xi]   * (1-tx)*(1-ty) +
                  density_arr[yi,   xi+1] *    tx *(1-ty) +
                  density_arr[yi+1, xi]   * (1-tx)*   ty  +
                  density_arr[yi+1, xi+1] *    tx *   ty)
            elev[ri, ci] = float(v) * max_height

    return elev, xs, ys, cell_x, cell_y


def triangle_normal(v0, v1, v2):
    """Compute unit normal of a triangle."""
    a = v1 - v0
    b = v2 - v0
    n = np.cross(a, b)
    length = np.linalg.norm(n)
    if length < 1e-10:
        return np.array([0.0, 0.0, 1.0])
    return n / length


def write_stl_binary(path: Path, triangles) -> int:
    """
    Write binary STL file.
    triangles: list of (normal, v0, v1, v2) where each is np.array(3).
    Returns triangle count.
    """
    header = b'LLE V2 terrain export' + b'\x00' * (80 - 21)
    with open(path, 'wb') as f:
        f.write(header)
        f.write(struct.pack('<I', len(triangles)))
        for normal, v0, v1, v2 in triangles:
            f.write(struct.pack('<fff', *normal))
            f.write(struct.pack('<fff', *v0))
            f.write(struct.pack('<fff', *v1))
            f.write(struct.pack('<fff', *v2))
            f.write(struct.pack('<H', 0))  # attribute byte count
    return len(triangles)


def build_triangles(elev, grid_size: int, cell_x: float, cell_y: float):
    """
    Build triangle list from heightfield.
    Physical units: X and Y in inches (cell_x × cell_y per cell),
    Z in inches (elev values).
    """
    triangles = []
    for ri in range(grid_size - 1):
        for ci in range(grid_size - 1):
            x0, y0 = ci * cell_x, ri * cell_y
            x1, y1 = (ci+1) * cell_x, ri * cell_y
            x2, y2 = ci * cell_x, (ri+1) * cell_y
            x3, y3 = (ci+1) * cell_x, (ri+1) * cell_y
            z00 = elev[ri,   ci]
            z10 = elev[ri,   ci+1]
            z01 = elev[ri+1, ci]
            z11 = elev[ri+1, ci+1]

            v00 = np.array([x0, y0, z00])
            v10 = np.array([x1, y1, z10])
            v01 = np.array([x2, y2, z01])
            v11 = np.array([x3, y3, z11])

            # Two triangles per cell
            n0 = triangle_normal(v00, v10, v01)
            triangles.append((n0, v00, v10, v01))

            n1 = triangle_normal(v10, v11, v01)
            triangles.append((n1, v10, v11, v01))

    return triangles


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export terrain patch as STL mesh.")
    parser.add_argument('--title',        default='terrain')
    parser.add_argument('--grid-size',    type=int,   default=EXPORT_DEFAULT_GRID_SIZE)
    parser.add_argument('--base-size',    type=float, default=EXPORT_DEFAULT_BASE_INCHES)
    parser.add_argument('--max-height',   type=float, default=EXPORT_DEFAULT_MAX_HEIGHT_INCHES)
    parser.add_argument('--focus-x',      type=float, default=None)
    parser.add_argument('--focus-y',      type=float, default=None)
    parser.add_argument('--focus-radius', type=float, default=None)
    parser.add_argument('--output-dir',   default='backend/data/exports/')
    args = parser.parse_args()

    # Input validation
    if args.grid_size < 4 or args.grid_size > EXPORT_MAX_GRID_DIMENSION:
        print(f"ERROR: grid_size must be 4\u2013{EXPORT_MAX_GRID_DIMENSION}.")
        sys.exit(1)
    if args.base_size <= 0 or args.base_size > 120:
        print("ERROR: base_size must be between 0 and 120 inches.")
        sys.exit(1)
    if args.max_height <= 0 or args.max_height > 120:
        print("ERROR: max_height must be between 0 and 120 inches.")
        sys.exit(1)

    title = sanitize_title(args.title)
    try:
        output_dir = safe_output_dir(args.output_dir)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if not TERRAIN_FILE.exists():
        print(f"ERROR: {TERRAIN_FILE} not found.")
        sys.exit(1)

    print("Loading terrain data ...")
    with open(TERRAIN_FILE, encoding='utf-8') as f:
        terrain = json.load(f)

    print(f"Sampling heightfield to {args.grid_size}\xd7{args.grid_size} ...")
    elev, xs, ys, cell_x, cell_y = build_heightfield(
        density=      terrain['density'],
        x_grid=       terrain['x_grid'],
        y_grid=       terrain['y_grid'],
        grid_size=    args.grid_size,
        base_size=    args.base_size,
        max_height=   args.max_height,
        focus_x=      args.focus_x,
        focus_y=      args.focus_y,
        focus_radius= args.focus_radius,
    )

    print("Building triangle mesh ...")
    triangles = build_triangles(elev, args.grid_size, cell_x, cell_y)
    n_tris    = len(triangles)
    print(f"  Triangles: {n_tris:,}")

    ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
    stl_path = output_dir / f"{title.replace(' ', '_')}_{ts}.stl"
    write_stl_binary(stl_path, triangles)

    size_kb = stl_path.stat().st_size // 1024
    print(f"\nSTL export complete:")
    print(f"  File:       {stl_path}")
    print(f"  Size:       {size_kb} KB")
    print(f"  Triangles:  {n_tris:,}")
    print(f"  Dimensions: {args.base_size}\" \xd7 {args.base_size}\" \xd7 {args.max_height}\"")
    print(f"  Note: mesh is a surface only (open bottom).")
    print(f"        Add a solid base in CAD software for fabrication.")


if __name__ == "__main__":
    main()
