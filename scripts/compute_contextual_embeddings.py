"""
compute_contextual_embeddings.py
Compute contextual embedding vectors for all vocabulary terms.

For each term, encode 7 sentences -- one per CONTEXT_TEMPLATES key
(abstract_relations, space, matter, intellect, volition, affections, neutral).

Output: data/embeddings/contextual_embeddings.npz
  - terms:           string array (N,)
  - embeddings:      float32 array (N, 7, 384)
                     axis 0: terms (same order as base_embeddings.npz)
                     axis 1: context index (0=abstract_relations, ..., 6=neutral)
                     axis 2: embedding dimensions
  - spreads:         float32 array (N,) -- mean pairwise L2 distance
  - polysemy_scores: float32 array (N,) -- spreads normalized to [0, 1]

Also writes: data/embeddings/contextual_meta.json
  - context_keys: ordered list of template names (matches axis 1)
  - mean_spread, max_spread, term_count, timestamp
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
VOCAB_FILE     = PROJECT_ROOT / "data" / "roget" / "vocab_validated.json"
BASE_NPZ       = PROJECT_ROOT / "data" / "embeddings" / "base_embeddings.npz"
EMBED_DIR      = PROJECT_ROOT / "data" / "embeddings"
OUTPUT_NPZ     = EMBED_DIR / "contextual_embeddings.npz"
OUTPUT_META    = EMBED_DIR / "contextual_meta.json"
CHECKPOINT_NPZ = EMBED_DIR / "contextual_checkpoint.npz"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import CONTEXT_TEMPLATES

MODEL_NAME   = "all-MiniLM-L6-v2"
BATCH_SIZE   = 256  # Smaller batches: 7x sentences per term
CONTEXT_KEYS = list(CONTEXT_TEMPLATES.keys())  # Stable order


def compute_spread(context_vecs: np.ndarray) -> float:
    """
    Mean pairwise L2 distance between context vectors for one term.
    context_vecs: shape (7, 384)
    Returns a scalar spread value.
    """
    n = context_vecs.shape[0]
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += np.linalg.norm(context_vecs[i] - context_vecs[j])
            count += 1
    return float(total / max(count, 1))


def main():
    for f in [VOCAB_FILE, BASE_NPZ]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed.")
        sys.exit(1)

    # Load term order from base embeddings
    print("Loading base embeddings (for term order) ...")
    base_data = np.load(BASE_NPZ, allow_pickle=True)
    terms     = list(base_data["terms"])
    total     = len(terms)
    print(f"Total terms: {total:,}")
    print(f"Context keys: {CONTEXT_KEYS}")

    # Load checkpoint
    if CHECKPOINT_NPZ.exists():
        ckpt    = np.load(CHECKPOINT_NPZ, allow_pickle=True)
        done    = int(ckpt["done_count"])
        ctx_emb = ckpt["embeddings"]  # shape (done, 7, 384)
        print(f"  Checkpoint: {done:,} terms already computed.")
    else:
        done    = 0
        ctx_emb = np.empty((0, len(CONTEXT_KEYS), 384), dtype=np.float32)

    if done < total:
        print(f"\nLoading model: {MODEL_NAME} ...")
        model = SentenceTransformer(MODEL_NAME)
        print("Model loaded.")

        new_embeddings = []
        t_start        = time.time()

        for idx in range(done, total):
            term = terms[idx]
            # Build 7 sentences, one per template
            sentences = [
                CONTEXT_TEMPLATES[key].format(term=term)
                for key in CONTEXT_KEYS
            ]
            vecs = model.encode(
                sentences,
                batch_size=len(sentences),
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=False,
            ).astype(np.float32)
            new_embeddings.append(vecs)  # shape (7, 384)

            # Progress and checkpoint every 2,000 terms
            completed = idx - done + 1
            if completed % 2000 == 0 or idx == total - 1:
                elapsed = time.time() - t_start
                rate    = completed / max(elapsed, 1)
                eta     = (total - done - completed) / max(rate, 1)
                print(f"  {idx + 1:,}/{total:,} "
                      f"({100*(idx+1)//total}%) "
                      f"-- {rate:.0f} terms/s -- ETA {eta/60:.1f} min")

                # Save checkpoint
                combined = np.vstack([
                    ctx_emb,
                    np.array(new_embeddings, dtype=np.float32),
                ])
                np.savez_compressed(
                    CHECKPOINT_NPZ,
                    embeddings=combined,
                    done_count=np.array(idx + 1),
                )

        final_embeddings = np.vstack([
            ctx_emb,
            np.array(new_embeddings, dtype=np.float32),
        ])
    else:
        print("All terms already computed from checkpoint.")
        final_embeddings = ctx_emb

    # Compute spread and polysemy scores
    print("\nComputing polysemy scores ...")
    spreads = np.array([
        compute_spread(final_embeddings[i])
        for i in range(len(terms))
    ], dtype=np.float32)

    max_spread      = float(spreads.max()) if spreads.max() > 0 else 1.0
    polysemy_scores = (spreads / max_spread).astype(np.float32)

    # Write output
    np.savez_compressed(
        OUTPUT_NPZ,
        terms=terms,
        embeddings=final_embeddings,   # (N, 7, 384)
        spreads=spreads,
        polysemy_scores=polysemy_scores,
    )

    meta = {
        "model":          MODEL_NAME,
        "embedding_dim":  384,
        "context_keys":   CONTEXT_KEYS,
        "n_contexts":     len(CONTEXT_KEYS),
        "term_count":     total,
        "mean_spread":    float(spreads.mean()),
        "max_spread":     max_spread,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "templates_used": CONTEXT_TEMPLATES,
    }
    with open(OUTPUT_META, "w") as f:
        json.dump(meta, f, indent=2)

    CHECKPOINT_NPZ.unlink(missing_ok=True)

    print(f"\nContextual embeddings complete:")
    print(f"  Shape:          {final_embeddings.shape}")
    print(f"  Mean spread:    {spreads.mean():.4f}")
    print(f"  Max spread:     {spreads.max():.4f}")
    print(f"  High polysemy (spread > 0.5x max): "
          f"{int((polysemy_scores > 0.5).sum()):,} terms")

    # Show most polysemous terms
    top_idx = np.argsort(polysemy_scores)[::-1][:10]
    print(f"\n  Most polysemous terms (highest context spread):")
    for i in top_idx:
        print(f"    {terms[i]:<25} spread={spreads[i]:.4f}  polysemy={polysemy_scores[i]:.3f}")


if __name__ == "__main__":
    main()
