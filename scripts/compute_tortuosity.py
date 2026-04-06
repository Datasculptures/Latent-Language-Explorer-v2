"""
compute_tortuosity.py
Compute gradient-ascent path tortuosity for every concept in the vocabulary.

Tortuosity = (gradient-ascent path length in UMAP space)
           / (straight-line distance from concept to its attractor)

A value near 1.0 means the concept sits in a clear basin centre.
A high value means the concept is near a basin boundary, pulled by multiple attractors.

Requires (must run after compute_attractors.py):
  data/terrain/density_field.npz
  data/terrain/attractors.json
  data/embeddings/umap_positions.npz

Output:
  backend/data/tortuosity.json   — { "term": float, ... }
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
DENSITY_NPZ     = PROJECT_ROOT / "data" / "terrain" / "density_field.npz"
UMAP_NPZ        = PROJECT_ROOT / "data" / "embeddings" / "umap_positions.npz"
ATTRACTORS_JSON = PROJECT_ROOT / "data" / "terrain" / "attractors.json"
OUTPUT_JSON     = PROJECT_ROOT / "backend" / "data" / "tortuosity.json"


def umap_to_grid(ux, uy, x_grid, y_grid):
    """Return (col, row) grid indices for a UMAP position."""
    gc = int(np.argmin(np.abs(x_grid - ux)))
    gr = int(np.argmin(np.abs(y_grid - uy)))
    return gc, gr


def grid_to_umap(col, row, x_grid, y_grid):
    """Return (umap_x, umap_y) for grid (col, row) indices."""
    x = float(x_grid[min(col, len(x_grid) - 1)])
    y = float(y_grid[min(row, len(y_grid) - 1)])
    return x, y


def ascent_path_length(start_row, start_col, density, x_grid, y_grid):
    """
    Follow steepest 8-connected gradient ascent from (start_row, start_col).
    Returns (path_length_umap, end_row, end_col).
    path_length_umap is the sum of step distances in UMAP coordinate space.
    """
    res    = density.shape[0]
    cr, cc = start_row, start_col
    sx, sy = grid_to_umap(cc, cr, x_grid, y_grid)
    px, py = sx, sy
    total  = 0.0

    visited = set()
    visited.add((cr, cc))

    for _ in range(res * 2):
        best_val      = density[cr, cc]
        best_r, best_c = cr, cc
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = cr + dr, cc + dc
                if 0 <= nr < res and 0 <= nc < res:
                    if density[nr, nc] > best_val:
                        best_val  = density[nr, nc]
                        best_r, best_c = nr, nc

        if best_r == cr and best_c == cc:
            break  # local maximum reached
        if (best_r, best_c) in visited:
            break  # cycle guard

        cr, cc = best_r, best_c
        visited.add((cr, cc))
        nx, ny = grid_to_umap(cc, cr, x_grid, y_grid)
        total += float(np.hypot(nx - px, ny - py))
        px, py = nx, ny

    return total, cr, cc


def main():
    for f in [DENSITY_NPZ, UMAP_NPZ, ATTRACTORS_JSON]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    print("Loading fields ...")
    d_data  = np.load(DENSITY_NPZ, allow_pickle=True)
    density = d_data["density"]   # (res, res)
    x_grid  = d_data["x_grid"]
    y_grid  = d_data["y_grid"]
    res     = density.shape[0]

    u_data    = np.load(UMAP_NPZ, allow_pickle=True)
    positions = u_data["positions"]  # (N, 2)
    terms     = list(u_data["terms"])
    N         = len(terms)
    print(f"  {N:,} concepts, {res}x{res} grid")

    with open(ATTRACTORS_JSON, encoding="utf-8") as f:
        attr_data = json.load(f)
    attr_pos = {a["id"]: (a["umap_x"], a["umap_y"]) for a in attr_data["attractors"]}
    term_assignments = attr_data["term_assignments"]

    print("Computing tortuosity ...")
    t0 = time.time()
    tortuosity = {}

    for i, term in enumerate(terms):
        if i % 5000 == 0 and i > 0:
            elapsed = time.time() - t0
            rate    = i / elapsed
            remain  = (N - i) / rate
            print(f"  {i:,} / {N:,}  ({remain:.0f}s remaining)")

        ux, uy  = float(positions[i, 0]), float(positions[i, 1])
        gc, gr  = umap_to_grid(ux, uy, x_grid, y_grid)
        gc      = min(gc, res - 1)
        gr      = min(gr, res - 1)

        path_len, end_r, end_c = ascent_path_length(gr, gc, density, x_grid, y_grid)

        # Straight-line distance to the assigned attractor
        attr_id = term_assignments.get(term)
        if attr_id and attr_id in attr_pos:
            ax, ay = attr_pos[attr_id]
        else:
            ax, ay = grid_to_umap(end_c, end_r, x_grid, y_grid)

        straight = float(np.hypot(ax - ux, ay - uy))
        tort     = path_len / max(straight, 0.001)
        tortuosity[term] = round(tort, 4)

    elapsed = time.time() - t0
    vals = list(tortuosity.values())
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Range : {min(vals):.3f} – {max(vals):.3f}")
    print(f"  Mean  : {sum(vals)/len(vals):.3f}")
    print(f"  Median: {sorted(vals)[len(vals)//2]:.3f}")

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(tortuosity, f, separators=(",", ":"))
    size_mb = OUTPUT_JSON.stat().st_size / 1_048_576
    print(f"Wrote: {OUTPUT_JSON}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
