"""
enrich_wordnet.py
Enrich Roget categories with vocabulary from WordNet.

For each Roget category:
  1. Use the category name as the lookup term in WordNet
  2. Find all synsets for that term
  3. For each synset, collect: lemma names, direct hypernyms, direct hyponyms
  4. Filter collected terms through the same cascade as filter_vocab.py
  5. Add terms not already in the category (up to WORDNET_ENRICH_CAP new terms)
  6. Tag added terms with wordnet_enriched: true

Output: data/roget/roget_enriched.json
Also updates the meta.total_categories word counts.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE   = PROJECT_ROOT / "data" / "roget" / "roget_filtered.json"
OUTPUT_FILE  = PROJECT_ROOT / "data" / "roget" / "roget_enriched.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import VOCAB_MIN_TERM_LENGTH, VOCAB_WORDNET_HOP_DEPTH

WORDNET_ENRICH_CAP = 30  # Max new terms added per category from WordNet

try:
    from nltk.corpus import wordnet as wn
except ImportError:
    print("ERROR: NLTK not installed. Run: pip install nltk")
    print("Then: python3 -c \"import nltk; nltk.download('wordnet')\"")
    sys.exit(1)


def _is_valid_term(term: str) -> bool:
    """Apply the same filter rules as filter_vocab.py."""
    t = term.lower().strip()
    if len(t) < VOCAB_MIN_TERM_LENGTH:
        return False
    if re.search(r'\d', t):
        return False
    if '_' in t:
        # WordNet uses underscores for multi-word concepts — skip these
        return False
    normalized = t.replace('-', '')
    return normalized.isalpha()


def get_wordnet_terms(category_name: str) -> list[str]:
    """
    Get related terms from WordNet for a category name.
    Returns lowercased single-word terms from synsets + 1-hop relations.
    """
    # Normalize category name for WordNet lookup
    lookup = category_name.lower().replace(' ', '_').replace('-', '_')
    # Try exact match first, then individual words in the name
    synsets = wn.synsets(lookup)
    if not synsets:
        for word in category_name.lower().split():
            synsets = wn.synsets(word)
            if synsets:
                break

    if not synsets:
        return []

    collected: set[str] = set()

    for synset in synsets[:3]:  # Limit to first 3 synsets to avoid noise
        # Synset lemmas
        for lemma in synset.lemmas():
            collected.add(lemma.name())

        if VOCAB_WORDNET_HOP_DEPTH >= 1:
            # Direct hypernyms (more general)
            for hypernym in synset.hypernyms()[:3]:
                for lemma in hypernym.lemmas():
                    collected.add(lemma.name())
            # Direct hyponyms (more specific)
            for hyponym in synset.hyponyms()[:5]:
                for lemma in hyponym.lemmas():
                    collected.add(lemma.name())

    # Filter and normalize
    valid = []
    for term in collected:
        t = term.lower().replace('_', ' ')
        # Single word only (no spaces)
        if ' ' not in t and _is_valid_term(t):
            valid.append(t)

    return valid


def enrich_category(cat: dict) -> int:
    """Add WordNet terms to a category. Returns count of terms added."""
    # Build set of already-present terms
    existing = {
        w["term"] for w in cat["words"]
        if isinstance(w, dict) and w.get("kept", False)
    }

    new_terms = get_wordnet_terms(cat["name"])
    added = 0

    for term in new_terms:
        if added >= WORDNET_ENRICH_CAP:
            break
        if term in existing:
            continue
        cat["words"].append({
            "term":                  term,
            "original":              term,
            "obsolete":              False,
            "flagged_proper_noun":   False,
            "kept":                  True,
            "wordnet_enriched":      True,
        })
        existing.add(term)
        added += 1

    return added


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run filter_vocab.py first.")
        sys.exit(1)

    print(f"Loading {INPUT_FILE} ...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_added   = 0
    cats_enriched = 0
    total_cats    = 0

    for cls in data["classes"]:
        for sec in cls["sections"]:
            for cat in sec["categories"]:
                total_cats += 1
                added = enrich_category(cat)
                if added > 0:
                    total_added += added
                    cats_enriched += 1
                if total_cats % 100 == 0:
                    print(f"  Processed {total_cats} categories, added {total_added} terms so far...")

    # Update meta
    total_kept = sum(
        1 for cls in data["classes"]
        for sec in cls["sections"]
        for cat in sec["categories"]
        for w in cat["words"]
        if isinstance(w, dict) and w.get("kept", False)
    )
    data["meta"]["enrich_timestamp"] = datetime.now(timezone.utc).isoformat()
    data["meta"]["wordnet_terms_added"] = total_added
    data["meta"]["kept_words_after_enrichment"] = total_kept

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nWordNet enrichment complete:")
    print(f"  Categories processed: {total_cats:,}")
    print(f"  Categories enriched:  {cats_enriched:,}")
    print(f"  Terms added:          {total_added:,}")
    print(f"  Total kept terms:     {total_kept:,}")
    print(f"Wrote: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
