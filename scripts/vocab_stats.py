"""
vocab_stats.py
Generate a vocabulary statistics report for Phase 1.
Prints to terminal and writes data/roget/vocab_stats.json.
This is the record of what Phase 1 produced.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
VALIDATED_FILE = PROJECT_ROOT / "data" / "roget" / "vocab_validated.json"
INDEX_FILE     = PROJECT_ROOT / "data" / "roget" / "vocab_index.json"
MODERN_FILE    = PROJECT_ROOT / "data" / "roget" / "roget_modern.json"
STATS_FILE     = PROJECT_ROOT / "data" / "roget" / "vocab_stats.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import ROGET_CLASSES


def main():
    for f in [VALIDATED_FILE, INDEX_FILE, MODERN_FILE]:
        if not f.exists():
            print(f"ERROR: {f} not found. Run all Phase 1 scripts first.")
            sys.exit(1)

    with open(VALIDATED_FILE, 'r') as f:
        vocab = json.load(f)
    with open(INDEX_FILE, 'r') as f:
        index = json.load(f)
    with open(MODERN_FILE, 'r') as f:
        roget = json.load(f)

    total      = len(vocab)
    polysemous = sum(1 for v in vocab if v["is_polysemous"])
    modern     = sum(1 for v in vocab if v["is_modern_addition"])
    obsolete   = sum(1 for v in vocab if v["is_obsolete"])
    wordnet    = sum(
        1 for cls in roget["classes"]
        for sec in cls["sections"]
        for cat in sec["categories"]
        for w in cat.get("words", [])
        if isinstance(w, dict) and w.get("kept") and w.get("wordnet_enriched")
    )

    by_class: dict[int, int] = Counter()
    for v in vocab:
        by_class[v["primary_class_id"]] += 1

    cats_with_terms: dict[str, int] = Counter()
    for v in vocab:
        cats_with_terms[v["primary_category_id"]] += 1

    populated_cats  = len(cats_with_terms)
    total_cats      = sum(
        len(sec["categories"])
        for cls in roget["classes"]
        for sec in cls["sections"]
    )
    median_cat_size = sorted(cats_with_terms.values())[len(cats_with_terms)//2] if cats_with_terms else 0
    max_cat         = max(cats_with_terms.values(), default=0)
    min_cat         = min(cats_with_terms.values(), default=0)

    print("=" * 60)
    print("Phase 1 Vocabulary Statistics")
    print("=" * 60)
    print(f"\nOverall")
    print(f"  Total terms (validated):  {total:,}")
    print(f"  Polysemous terms:         {polysemous:,} ({100*polysemous//max(total,1)}%)")
    print(f"  Modern additions:         {modern:,}")
    print(f"  WordNet enriched:         {wordnet:,}")
    print(f"  Obsolete (kept, flagged): {obsolete:,}")
    print(f"\nTaxonomy coverage")
    print(f"  Total categories:         {total_cats:,}")
    print(f"  Categories with terms:    {populated_cats:,}")
    print(f"  Median terms per cat:     {median_cat_size}")
    print(f"  Max terms in one cat:     {max_cat}")
    print(f"  Min terms in one cat:     {min_cat}")
    print(f"\nBy Roget class")
    for cls_id, cls_name in ROGET_CLASSES.items():
        count = by_class.get(cls_id, 0)
        pct   = 100 * count // max(total, 1)
        print(f"  Class {cls_id} {cls_name:<25} {count:>6,} ({pct}%)")

    print(f"\nKnown biases (document these, do not hide them)")
    print(f"  - Victorian English vocabulary from 1911 source")
    print(f"  - Western philosophical tradition (Leibniz/Aristotle structure)")
    print(f"  - Post-1911 domains supplemented but may still be underrepresented")
    print(f"  - Obsolete terms retained but flagged -- {obsolete} total")

    stats = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_terms": total,
        "polysemous": polysemous,
        "modern_additions": modern,
        "wordnet_enriched": wordnet,
        "obsolete_kept": obsolete,
        "total_categories": total_cats,
        "populated_categories": populated_cats,
        "median_terms_per_category": median_cat_size,
        "max_terms_per_category": max_cat,
        "by_class": {
            str(k): {"name": v, "count": by_class.get(k, 0)}
            for k, v in ROGET_CLASSES.items()
        },
        "known_biases": [
            "Victorian English vocabulary from 1911 source",
            "Western philosophical tradition (Leibniz/Aristotle structure)",
            "Post-1911 domains supplemented via modern domain scripts",
            "Obsolete terms retained and flagged",
        ],
    }

    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"\nWrote: {STATS_FILE}")


if __name__ == "__main__":
    main()
