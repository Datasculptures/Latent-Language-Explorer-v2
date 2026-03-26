"""
compute_context_positions.py
Compute 2D UMAP-space positions for each of the 7 contextual embedding
variants per vocabulary term, so the atmosphere layer can place satellite
spheres at meaningful offsets from the base concept position.

Algorithm (simple fallback, acceptable for V2):
  For each term, run PCA on its 7 context vectors (7 × 384) to obtain
  2D relative coordinates.  Normalize to unit std, then scale by
  polysemy_score × 0.5 so variants stay visually close to the base.
  Add the term's base UMAP position to get absolute 2D positions.

Run order: after compute_umap.py, before assemble_bundle.py.

Output: backend/data/context_positions.json
  Schema: { term: [[x,y], [x,y], [x,y], [x,y], [x,y], [x,y], [x,y]] }
  One [x,y] per context template in CONTEXT_TEMPLATES order:
    0  abstract_relations
    1  space
    2  matter
    3  intellect
    4  volition
    5  affections
    6  neutral
"""

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UMAP_NPZ     = PROJECT_ROOT / "data" / "embeddings" / "umap_positions.npz"
CTX_NPZ      = PROJECT_ROOT / "data" / "embeddings" / "contextual_embeddings.npz"
OUTPUT_FILE  = PROJECT_ROOT / "backend" / "data" / "context_positions.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import CONTEXT_TEMPLATES

CONTEXT_KEYS = list(CONTEXT_TEMPLATES.keys())  # Stable order, 7 keys
N_CONTEXTS   = len(CONTEXT_KEYS)               # 7


def pca_2d(vecs: np.ndarray) -> np.ndarray:
    """
    Project (7, 384) context vectors to (7, 2) relative 2-D coordinates via PCA.
    Returns a (7, 2) zero array if the vectors are degenerate (all identical).
    """
    mean    = vecs.mean(axis=0)
    centered = vecs - mean  # (7, 384)
    try:
        U, S, _ = np.linalg.svd(centered, full_matrices=False)
        # U: (7, 7), S: (7,)
        # PCA scores for the first two principal components
        coords = U[:, :2] * S[:2]  # (7, 2)
    except np.linalg.LinAlgError:
        return np.zeros((N_CONTEXTS, 2), dtype=np.float32)

    # Normalize to unit std so polysemy_score controls the actual spatial scale
    std = float(coords.std())
    if std > 1e-8:
        coords = coords / std
    return coords.astype(np.float32)


def main():
    for f in [UMAP_NPZ, CTX_NPZ]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            print("Run compute_umap.py and compute_contextual_embeddings.py first.")
            sys.exit(1)

    print("Loading UMAP positions ...")
    umap_data = np.load(UMAP_NPZ, allow_pickle=True)
    umap_terms = list(umap_data["terms"])
    positions  = umap_data["positions"]  # (N, 2)

    print("Loading contextual embeddings ...")
    ctx_data        = np.load(CTX_NPZ, allow_pickle=True)
    ctx_terms       = list(ctx_data["terms"])
    ctx_embeddings  = ctx_data["embeddings"]    # (N, 7, 384)
    polysemy_scores = ctx_data["polysemy_scores"]  # (N,)

    total = len(ctx_terms)
    print(f"Terms: {total:,}  |  Context keys: {CONTEXT_KEYS}")

    pos_map = {t: positions[i] for i, t in enumerate(umap_terms)}

    output: dict[str, list] = {}
    skipped = 0

    for i, term in enumerate(ctx_terms):
        if term not in pos_map:
            skipped += 1
            continue

        base_xy    = pos_map[term]               # [x, y] in UMAP 2-D space
        poly_score = float(polysemy_scores[i])

        vecs_7  = ctx_embeddings[i]              # (7, 384)
        rel_2d  = pca_2d(vecs_7)                 # (7, 2) — normalised relative coords

        # Scale: polysemy_score × 0.5 UMAP units keeps variants near the base
        # while spreading high-polysemy terms further apart.
        scale  = poly_score * 0.5
        abs_2d = rel_2d * scale + base_xy        # (7, 2) — absolute UMAP position

        output[term] = [
            [round(float(abs_2d[j, 0]), 6), round(float(abs_2d[j, 1]), 6)]
            for j in range(N_CONTEXTS)
        ]

        if (i + 1) % 5000 == 0 or i == total - 1:
            print(f"  {i + 1:,}/{total:,} ({100*(i+1)//total}%)")

    if skipped:
        print(f"  Skipped {skipped:,} terms with no UMAP position.")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1e6
    print(f"\nWrote: {OUTPUT_FILE}")
    print(f"  {len(output):,} terms, {N_CONTEXTS} positions each  ({size_mb:.1f} MB)")
    print(f"\nNext: run assemble_bundle.py to embed positions into the data bundle.")


if __name__ == "__main__":
    main()
