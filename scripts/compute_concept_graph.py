"""
compute_concept_graph.py
Precomputes a k-nearest-neighbour graph over concept UMAP positions.
Output: backend/data/concept_graph.json

Run once after the data pipeline:
  py scripts/compute_concept_graph.py

The graph is consumed by POST /api/path for Dijkstra shortest-path queries.
"""
import sys, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, "C:/Users/SeanP/OneDrive - mapleclose.ca/Sean/AI/LLEv2/Lib/site-packages")

import numpy as np
from scipy.spatial import KDTree

K = 6  # neighbours per node

def main():
    bundle_path = PROJECT_ROOT / "backend" / "data" / "data_bundle.json"
    out_path    = PROJECT_ROOT / "backend" / "data" / "concept_graph.json"

    print(f"Loading {bundle_path.name} ...")
    with open(bundle_path, encoding="utf-8") as f:
        bundle = json.load(f)

    concepts = bundle["concepts"]
    n = len(concepts)
    print(f"  {n} concepts")

    terms     = [c["label"]       for c in concepts]
    positions = [[c["position_2d"][0], c["position_2d"][1]] for c in concepts]
    pos_arr   = np.array(positions, dtype=np.float32)

    print(f"Building KDTree and querying {K}-NN ...")
    t0 = time.time()
    tree = KDTree(pos_arr)
    # k+1 because the nearest neighbour of a point is itself
    dists, indices = tree.query(pos_arr, k=K + 1)
    print(f"  done in {time.time()-t0:.1f}s")

    # Build adjacency list (skip self at index 0)
    # Format: adj[i] = [j0, d0, j1, d1, ...] as flat list (ints and floats alternating)
    adj = []
    for i in range(n):
        row = []
        for slot in range(1, K + 1):
            j = int(indices[i, slot])
            d = float(dists[i, slot])
            row.append(j)
            row.append(round(d, 6))
        adj.append(row)

    out = {
        "meta": {
            "node_count": n,
            "k": K,
        },
        "terms":     terms,
        "positions": [[round(p[0], 6), round(p[1], 6)] for p in positions],
        "adj":       adj,
    }

    print(f"Writing {out_path.name} ...")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    size_mb = out_path.stat().st_size / 1_048_576
    print(f"  wrote {size_mb:.1f} MB  ({n} nodes, {n*K} edges)")
    print("Done.")

if __name__ == "__main__":
    main()
