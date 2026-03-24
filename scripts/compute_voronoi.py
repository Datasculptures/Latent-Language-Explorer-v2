"""
compute_voronoi.py
Voronoi decomposition of concept positions in 2D UMAP space.

Voronoi vertices are the points equidistant from 3+ concepts --
the mathematically most interstitial locations. These form the
Absence Catalogue: ranked by equidistance, they represent the
purest "gaps" in the vocabulary.

Output: backend/data/voronoi_data.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.spatial import Voronoi

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UMAP_NPZ     = PROJECT_ROOT / "data" / "embeddings" / "umap_positions.npz"
BUNDLE_FILE  = PROJECT_ROOT / "backend" / "data" / "data_bundle.json"
OUTPUT_JSON  = PROJECT_ROOT / "backend" / "data" / "voronoi_data.json"

MAX_VERTICES = 5000  # Cap for frontend performance


def main():
    for f in [UMAP_NPZ, BUNDLE_FILE]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    print("Loading UMAP positions ...")
    umap_data = np.load(UMAP_NPZ, allow_pickle=True)
    positions = umap_data["positions"]  # (N, 2)
    terms     = list(umap_data["terms"])
    N         = len(terms)

    print("Loading concept metadata ...")
    with open(BUNDLE_FILE, encoding="utf-8") as f:
        bundle = json.load(f)
    term_to_meta = {c["label"]: c for c in bundle["concepts"]}

    print(f"Computing Voronoi decomposition of {N:,} points ...")
    vor = Voronoi(positions)

    # UMAP bounding box for clipping
    x_min, x_max = float(positions[:, 0].min()), float(positions[:, 0].max())
    y_min, y_max = float(positions[:, 1].min()), float(positions[:, 1].max())
    margin  = 0.1
    x_range = [x_min - margin*(x_max-x_min), x_max + margin*(x_max-x_min)]
    y_range = [y_min - margin*(y_max-y_min), y_max + margin*(y_max-y_min)]

    def in_bounds(pt):
        return (x_range[0] <= pt[0] <= x_range[1] and
                y_range[0] <= pt[1] <= y_range[1])

    # Map: vertex_idx -> set of concept indices that share it
    vertex_concepts: dict[int, set[int]] = {}
    for (pt_a, pt_b), (v_a, v_b) in zip(vor.ridge_points, vor.ridge_vertices):
        for v in [v_a, v_b]:
            if v == -1:  # Infinite ridge
                continue
            vertex_concepts.setdefault(v, set()).update([pt_a, pt_b])

    # Build vertex list with equidistance scores
    vertices = []
    for v_idx, concept_set in vertex_concepts.items():
        v_pos = vor.vertices[v_idx]
        if not in_bounds(v_pos):
            continue

        concept_indices = list(concept_set)
        if len(concept_indices) < 3:
            continue  # Not a genuine vertex (only 2 parent concepts)

        dists = [
            float(np.linalg.norm(v_pos - positions[ci]))
            for ci in concept_indices
        ]
        mean_dist    = float(np.mean(dists))
        std_dist     = float(np.std(dists))
        equidistance = mean_dist / max(std_dist + 1e-8, 1e-4)

        parent_terms = []
        for ci in concept_indices[:6]:
            if ci < len(terms):
                t    = terms[ci]
                meta = term_to_meta.get(t, {})
                parent_terms.append({
                    "term":          t,
                    "distance":      float(np.linalg.norm(v_pos - positions[ci])),
                    "class_id":      meta.get("roget_class_id"),
                    "class_name":    meta.get("roget_class_name"),
                    "category_name": meta.get("roget_category_name"),
                })

        vertices.append({
            "id":           f"vor_{v_idx}",
            "x":            float(v_pos[0]),
            "y":            float(v_pos[1]),
            "equidistance": equidistance,
            "mean_dist":    mean_dist,
            "parent_count": len(concept_indices),
            "parents":      sorted(parent_terms, key=lambda p: p["distance"])[:5],
        })

    # Sort by equidistance descending (most interstitial first)
    vertices.sort(key=lambda v: v["equidistance"], reverse=True)

    if len(vertices) > MAX_VERTICES:
        print(f"  Capping at {MAX_VERTICES} vertices (found {len(vertices)})")
        vertices = vertices[:MAX_VERTICES]

    for i, v in enumerate(vertices):
        v["rank"] = i + 1

    result = {
        "meta": {
            "concept_count": N,
            "vertex_count":  len(vertices),
            "max_vertices":  MAX_VERTICES,
            "timestamp":     datetime.now(timezone.utc).isoformat(),
        },
        "vertices": vertices,
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nVoronoi vertices: {len(vertices)}")
    if vertices:
        print(f"  Top vertex: ({vertices[0]['x']:.3f}, {vertices[0]['y']:.3f})")
        print(f"  equidistance={vertices[0]['equidistance']:.3f}")
        print(f"  parents: {[p['term'] for p in vertices[0]['parents'][:3]]}")
    print(f"Wrote: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
