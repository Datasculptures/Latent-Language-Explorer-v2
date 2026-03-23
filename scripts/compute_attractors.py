"""
compute_attractors.py
Identify attractor peaks and assign each concept to an attractor basin
via gradient ascent on the density field.

Algorithm:
  For each grid cell, follow the steepest-ascent neighbour (8-connected)
  until reaching a local maximum. Local maxima with similar positions
  are merged (Union-Find, within MERGE_RADIUS grid cells).

Each vocabulary term is assigned to the basin of its nearest grid cell's
attractor.

Output: data/terrain/attractors.json
  - attractors: list of {id, grid_row, grid_col, umap_x, umap_y, density,
                          term_count, fraction, is_major}
  - term_assignments: {term: attractor_id}
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DENSITY_NPZ  = PROJECT_ROOT / "data" / "terrain" / "density_field.npz"
GRADIENT_NPZ = PROJECT_ROOT / "data" / "terrain" / "gradient_field.npz"
UMAP_NPZ     = PROJECT_ROOT / "data" / "embeddings" / "umap_positions.npz"
TERRAIN_DIR  = PROJECT_ROOT / "data" / "terrain"
OUTPUT_JSON  = TERRAIN_DIR / "attractors.json"

MERGE_RADIUS = 2    # Grid cells within this radius are merged into one peak
MAJOR_THRESH = 0.1  # Attractors with >= this fraction of total terms are "major"


class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x, y):
        self.parent[self.find(x)] = self.find(y)


def grid_to_umap(gx, gy, x_grid, y_grid):
    """Convert grid indices (col, row) to UMAP coordinates."""
    x = float(x_grid[min(gx, len(x_grid) - 1)])
    y = float(y_grid[min(gy, len(y_grid) - 1)])
    return x, y


def umap_to_grid(ux, uy, x_grid, y_grid):
    """Convert UMAP coordinates to nearest grid indices (col, row)."""
    gx = int(np.argmin(np.abs(x_grid - ux)))
    gy = int(np.argmin(np.abs(y_grid - uy)))
    return gx, gy


def main():
    for f in [DENSITY_NPZ, GRADIENT_NPZ, UMAP_NPZ]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    print("Loading fields ...")
    d_data  = np.load(DENSITY_NPZ, allow_pickle=True)
    density = d_data["density"]   # (128, 128)
    x_grid  = d_data["x_grid"]
    y_grid  = d_data["y_grid"]
    res     = density.shape[0]

    u_data    = np.load(UMAP_NPZ, allow_pickle=True)
    positions = u_data["positions"]  # (N, 2)
    terms     = list(u_data["terms"])
    N         = len(terms)
    print(f"Grid: {res}x{res}, Terms: {N:,}")

    # -- Gradient ascent from every grid cell --------------------------------
    # cell_peak[r, c] = (peak_r, peak_c) after ascent
    print("Running gradient ascent on all grid cells ...")
    cell_peak = np.zeros((res, res, 2), dtype=np.int32)

    for r in range(res):
        for c in range(res):
            cr, cc = r, c
            for _ in range(res * 2):  # max steps
                best_val = density[cr, cc]
                best_r, best_c = cr, cc
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = cr + dr, cc + dc
                        if 0 <= nr < res and 0 <= nc < res:
                            if density[nr, nc] > best_val:
                                best_val = density[nr, nc]
                                best_r, best_c = nr, nc
                if best_r == cr and best_c == cc:
                    break  # Local maximum
                cr, cc = best_r, best_c
            cell_peak[r, c] = [cr, cc]

    # -- Find unique peaks ---------------------------------------------------
    peaks = list(set(map(tuple, cell_peak.reshape(-1, 2).tolist())))
    print(f"Found {len(peaks)} raw peaks before merging.")

    # -- Merge nearby peaks (Union-Find) ------------------------------------
    uf       = UnionFind(len(peaks))
    peak_idx = {p: i for i, p in enumerate(peaks)}
    for i, (r1, c1) in enumerate(peaks):
        for j, (r2, c2) in enumerate(peaks):
            if i >= j:
                continue
            if abs(r1 - r2) <= MERGE_RADIUS and abs(c1 - c2) <= MERGE_RADIUS:
                uf.union(i, j)

    # Canonical peak per group: the one with highest density
    groups: dict[int, list] = defaultdict(list)
    for i, p in enumerate(peaks):
        groups[uf.find(i)].append(p)

    canonical: dict[int, tuple] = {}
    for root, members in groups.items():
        canonical[root] = max(members, key=lambda p: density[p[0], p[1]])

    unique_peaks = list(set(canonical.values()))
    print(f"After merging: {len(unique_peaks)} attractors.")

    # -- Map each cell to its canonical attractor ----------------------------
    cell_attractor = {}
    for r in range(res):
        for c in range(res):
            raw     = tuple(cell_peak[r, c].tolist())
            raw_idx = peak_idx[raw]
            canon   = canonical[uf.find(raw_idx)]
            cell_attractor[(r, c)] = canon

    # -- Assign each term to its nearest grid cell's attractor --------------
    term_assignments = {}
    attractor_terms: dict[tuple, list] = defaultdict(list)

    for i, term in enumerate(terms):
        ux, uy = positions[i]
        gx, gy = umap_to_grid(ux, uy, x_grid, y_grid)
        gx = min(gx, res - 1)
        gy = min(gy, res - 1)
        attr = cell_attractor[(gy, gx)]  # (row, col) = (y, x)
        term_assignments[term] = f"{attr[0]}_{attr[1]}"
        attractor_terms[attr].append(term)

    # -- Build attractor list ------------------------------------------------
    attractors = []
    for peak_rc, terms_in_basin in sorted(
        attractor_terms.items(), key=lambda x: -len(x[1])
    ):
        pr, pc = peak_rc
        ux, uy = grid_to_umap(pc, pr, x_grid, y_grid)
        frac   = len(terms_in_basin) / max(N, 1)
        attractors.append({
            "id":         f"{pr}_{pc}",
            "grid_row":   int(pr),
            "grid_col":   int(pc),
            "umap_x":     float(ux),
            "umap_y":     float(uy),
            "density":    float(density[pr, pc]),
            "term_count": len(terms_in_basin),
            "fraction":   float(frac),
            "is_major":   frac >= MAJOR_THRESH,
        })

    major_count = sum(1 for a in attractors if a["is_major"])
    print(f"Major attractors (>={100*MAJOR_THRESH:.0f}% of terms): {major_count}")
    print(f"Total attractors: {len(attractors)}")
    print(f"\nTop 10 attractors by term count:")
    for a in attractors[:10]:
        print(f"  [{a['id']}] density={a['density']:.3f}  "
              f"terms={a['term_count']:,} ({100*a['fraction']:.1f}%)  "
              f"major={a['is_major']}")

    result = {
        "meta": {
            "attractor_count":       len(attractors),
            "major_attractor_count": major_count,
            "merge_radius_cells":    MERGE_RADIUS,
            "major_threshold_frac":  MAJOR_THRESH,
            "timestamp":             datetime.now(timezone.utc).isoformat(),
        },
        "attractors":       attractors,
        "term_assignments": term_assignments,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nWrote: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
