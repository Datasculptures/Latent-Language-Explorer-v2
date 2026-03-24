"""
compute_base_embeddings.py
Compute base embedding vectors for all validated vocabulary terms.

One 384-dimensional vector per term, using the neutral context sentence.
Checkpoints every 5,000 terms so a restart does not lose progress.

Output: data/embeddings/base_embeddings.npz
  - embeddings: float32 array of shape (N, 384)
  - terms: string array of length N (matches vocab_validated.json order)

Also writes: data/embeddings/base_embeddings_meta.json
  - model, dimensions, term count, timestamp, sentence template used
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
VOCAB_FILE     = PROJECT_ROOT / "data" / "roget" / "vocab_validated.json"
EMBED_DIR      = PROJECT_ROOT / "data" / "embeddings"
OUTPUT_NPZ     = EMBED_DIR / "base_embeddings.npz"
OUTPUT_META    = EMBED_DIR / "base_embeddings_meta.json"
CHECKPOINT_NPZ = EMBED_DIR / "base_embeddings_checkpoint.npz"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import CONTEXT_TEMPLATES

MODEL_NAME       = "all-MiniLM-L6-v2"
BATCH_SIZE       = 512
NEUTRAL_TEMPLATE = CONTEXT_TEMPLATES["neutral"]  # "{term} is a concept..."


def load_checkpoint() -> tuple[list[str], np.ndarray] | None:
    """Load a partial checkpoint if it exists. Returns (terms, embeddings) or None."""
    if CHECKPOINT_NPZ.exists():
        data = np.load(CHECKPOINT_NPZ, allow_pickle=True)
        terms = list(data["terms"])
        embeddings = data["embeddings"]
        print(f"  Checkpoint found: {len(terms):,} terms already computed.")
        return terms, embeddings
    return None


def save_checkpoint(terms: list[str], embeddings: np.ndarray):
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CHECKPOINT_NPZ, terms=terms, embeddings=embeddings)


def main():
    if not VOCAB_FILE.exists():
        print(f"ERROR: {VOCAB_FILE} not found. Complete Phase 1 first.")
        sys.exit(1)

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed.")
        print("Run: pip install sentence-transformers")
        sys.exit(1)

    print(f"Loading vocabulary from {VOCAB_FILE} ...")
    with open(VOCAB_FILE, "r", encoding="utf-8") as f:
        vocab = json.load(f)

    all_terms = [v["term"] for v in vocab]
    total     = len(all_terms)
    print(f"Total terms: {total:,}")

    # Check checkpoint
    checkpoint = load_checkpoint()
    if checkpoint is not None:
        done_terms, done_embeddings = checkpoint
        done_set        = set(done_terms)
        remaining_vocab = [v for v in vocab if v["term"] not in done_set]
        print(f"  Remaining: {len(remaining_vocab):,} terms to compute.")
    else:
        done_terms, done_embeddings = [], np.empty((0, 384), dtype=np.float32)
        remaining_vocab = vocab

    if not remaining_vocab:
        print("All terms already computed. Loading checkpoint as final output.")
        final_terms      = done_terms
        final_embeddings = done_embeddings
    else:
        print(f"\nLoading model: {MODEL_NAME} ...")
        model = SentenceTransformer(MODEL_NAME)
        dim   = model.get_sentence_embedding_dimension()
        print(f"Model loaded. Embedding dimension: {dim}")

        # Build sentences for remaining terms
        sentences = [
            NEUTRAL_TEMPLATE.format(term=v["term"])
            for v in remaining_vocab
        ]

        print(f"\nEncoding {len(sentences):,} sentences in batches of {BATCH_SIZE} ...")
        t_start        = time.time()
        new_embeddings = []
        new_terms      = []

        for i in range(0, len(sentences), BATCH_SIZE):
            batch_sentences = sentences[i:i + BATCH_SIZE]
            batch_terms     = [v["term"] for v in remaining_vocab[i:i + BATCH_SIZE]]

            vecs = model.encode(
                batch_sentences,
                batch_size=BATCH_SIZE,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            new_embeddings.append(vecs.astype(np.float32))
            new_terms.extend(batch_terms)

            # Progress and checkpoint every 5,000 terms
            completed = len(new_terms)
            if completed % 5000 < BATCH_SIZE or i + BATCH_SIZE >= len(sentences):
                elapsed = time.time() - t_start
                rate    = completed / max(elapsed, 1)
                eta     = (len(sentences) - completed) / max(rate, 1)
                print(f"  {completed + len(done_terms):,}/{total:,} terms "
                      f"({100*(completed+len(done_terms))//total}%) "
                      f"-- {rate:.0f} terms/s -- ETA {eta/60:.1f} min")

                # Save checkpoint
                combined_terms      = done_terms + new_terms
                combined_embeddings = np.vstack([done_embeddings,
                                                 np.vstack(new_embeddings)])
                save_checkpoint(combined_terms, combined_embeddings)

        final_terms      = done_terms + new_terms
        final_embeddings = np.vstack([done_embeddings, np.vstack(new_embeddings)])

    # Verify order matches vocab_validated.json
    term_to_idx        = {t: i for i, t in enumerate(final_terms)}
    ordered_terms      = []
    ordered_embeddings = []
    for v in vocab:
        t = v["term"]
        if t in term_to_idx:
            ordered_terms.append(t)
            ordered_embeddings.append(final_embeddings[term_to_idx[t]])
        else:
            print(f"  WARNING: Term '{t}' missing from embeddings -- skipping.")

    final_terms      = ordered_terms
    final_embeddings = np.array(ordered_embeddings, dtype=np.float32)

    # Write final output
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUTPUT_NPZ, terms=final_terms, embeddings=final_embeddings)

    meta = {
        "model":             MODEL_NAME,
        "embedding_dim":     final_embeddings.shape[1],
        "term_count":        len(final_terms),
        "sentence_template": NEUTRAL_TEMPLATE,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_META, "w") as f:
        json.dump(meta, f, indent=2)

    # Clean up checkpoint
    CHECKPOINT_NPZ.unlink(missing_ok=True)

    print(f"\nBase embeddings complete:")
    print(f"  Terms:     {len(final_terms):,}")
    print(f"  Shape:     {final_embeddings.shape}")
    print(f"  Dtype:     {final_embeddings.dtype}")
    print(f"  Output:    {OUTPUT_NPZ}")
    print(f"\nSanity check -- first 5 terms and their L2 norms:")
    for i in range(min(5, len(final_terms))):
        norm = np.linalg.norm(final_embeddings[i])
        print(f"  [{i}] {final_terms[i]:<20} norm={norm:.4f}")


if __name__ == "__main__":
    main()
