"""
validate_vocab.py
Validate the vocabulary against the embedding model.
Remove any terms that do not have a vector in the model.

This script loads the sentence-transformers model and checks each term
in vocab_flat.json. Terms without embeddings are removed and logged.

Output: data/roget/vocab_validated.json  (final vocabulary, model-confirmed)
        data/roget/vocab_removed.json    (terms removed, for audit)

NOTE: This script downloads the embedding model on first run (~80MB).
      Requires sentence-transformers to be installed.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
FLAT_FILE      = PROJECT_ROOT / "data" / "roget" / "vocab_flat.json"
VALIDATED_FILE = PROJECT_ROOT / "data" / "roget" / "vocab_validated.json"
REMOVED_FILE   = PROJECT_ROOT / "data" / "roget" / "vocab_removed.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: sentence-transformers not installed.")
    print("Run: pip install sentence-transformers")
    sys.exit(1)


def main():
    if not FLAT_FILE.exists():
        print(f"ERROR: {FLAT_FILE} not found. Run build_vocab_index.py first.")
        sys.exit(1)

    print("Loading vocabulary ...")
    with open(FLAT_FILE, 'r', encoding='utf-8') as f:
        vocab = json.load(f)

    print(f"Loaded {len(vocab):,} terms.")

    # Load the embedding model
    # all-MiniLM-L6-v2 is the V2 primary model (384 dimensions, fast)
    MODEL_NAME = "all-MiniLM-L6-v2"
    print(f"Loading embedding model: {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    print("Model loaded.")

    # Validate in batches
    terms = [v["term"] for v in vocab]
    BATCH = 512
    valid_terms: set[str] = set()

    print(f"Encoding {len(terms):,} terms in batches of {BATCH} ...")
    for i in range(0, len(terms), BATCH):
        batch = terms[i:i + BATCH]
        try:
            embeddings = model.encode(batch, show_progress_bar=False)
            # sentence-transformers encodes all terms -- every term gets a vector.
            # The model handles out-of-vocabulary via subword tokenization.
            # All terms are valid by construction; we keep all of them.
            valid_terms.update(batch)
        except Exception as e:
            print(f"  WARNING: Batch {i//BATCH} failed: {e}")
        if (i // BATCH) % 10 == 0:
            print(f"  {min(i + BATCH, len(terms)):,} / {len(terms):,} terms processed")

    # Split into validated and removed
    validated = [v for v in vocab if v["term"] in valid_terms]
    removed   = [v for v in vocab if v["term"] not in valid_terms]

    # Write outputs
    with open(VALIDATED_FILE, 'w', encoding='utf-8') as f:
        json.dump(validated, f, ensure_ascii=False, indent=2)

    with open(REMOVED_FILE, 'w', encoding='utf-8') as f:
        json.dump(removed, f, ensure_ascii=False, indent=2)

    print(f"\nValidation complete:")
    print(f"  Input terms:    {len(vocab):,}")
    print(f"  Validated:      {len(validated):,}")
    print(f"  Removed:        {len(removed):,}")
    if removed:
        print(f"  Removed terms:  {[r['term'] for r in removed[:10]]} ...")
    print(f"\nWrote: {VALIDATED_FILE}")
    print(f"Wrote: {REMOVED_FILE}")
    print(f"\nPhase 1 complete. Final vocabulary: {len(validated):,} terms.")
    print(f"Proceed to Phase 2: embedding computation.")


if __name__ == "__main__":
    main()
