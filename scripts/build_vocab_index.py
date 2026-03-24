"""
build_vocab_index.py
Build the multi-category index and flat vocabulary list from the
modern-enriched Roget taxonomy.

Outputs:
  data/roget/vocab_index.json       -- per-term category membership
  data/roget/vocab_flat.json        -- flat list of all kept terms with metadata
  data/roget/category_colours.json  -- colour assignment per Roget class

vocab_index.json schema:
{
  "term": {
    "categories": ["1.1.1", "2.3.4"],
    "roget_class_ids": [1, 2],
    "is_polysemous": true,
    "is_modern_addition": false,
    "is_obsolete": false
  }
}

vocab_flat.json schema:
[
  {
    "term": "existence",
    "primary_category_id": "1.1.1",
    "primary_category_name": "Existence",
    "primary_section_name": "Abstract Existence",
    "primary_class_id": 1,
    "primary_class_name": "Abstract Relations",
    "all_category_ids": ["1.1.1"],
    "is_polysemous": false,
    "is_modern_addition": false,
    "is_obsolete": false,
    "colour": "#00b4d8"
  }
]
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE   = PROJECT_ROOT / "data" / "roget" / "roget_modern.json"
INDEX_FILE   = PROJECT_ROOT / "data" / "roget" / "vocab_index.json"
FLAT_FILE    = PROJECT_ROOT / "data" / "roget" / "vocab_flat.json"
COLOUR_FILE  = PROJECT_ROOT / "data" / "roget" / "category_colours.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import ROGET_CLASSES

# -- Colour assignments -------------------------------------------------------
# 6 base colours for the 6 Roget classes.
# These match the ROGET_CLASS_COLOURS in frontend/src/types/index.ts.
ROGET_CLASS_BASE_COLOURS = {
    1: "#00b4d8",  # Abstract Relations -- cyan
    2: "#e040a0",  # Space              -- magenta
    3: "#f07020",  # Matter             -- orange
    4: "#4ecb71",  # Intellect          -- green
    5: "#a070e0",  # Volition           -- violet
    6: "#e05050",  # Affections         -- warm red
}


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run add_modern_domains.py first.")
        sys.exit(1)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # -- Build term -> category mapping ---------------------------------------
    # term -> list of (category_id, category_name, section_name, class_id, class_name, is_modern, is_obsolete)
    term_map: dict[str, list[dict]] = defaultdict(list)

    for cls in data["classes"]:
        class_id   = cls["id"]
        class_name = cls["name"]
        for sec in cls["sections"]:
            section_name = sec["name"]
            for cat in sec["categories"]:
                cat_id   = cat["id"]
                cat_name = cat["name"]
                for word in cat.get("words", []):
                    if not isinstance(word, dict) or not word.get("kept", False):
                        continue
                    term = word["term"]
                    term_map[term].append({
                        "category_id":    cat_id,
                        "category_name":  cat_name,
                        "section_name":   section_name,
                        "class_id":       class_id,
                        "class_name":     class_name,
                        "is_modern":      word.get("is_modern_addition", False),
                        "is_obsolete":    word.get("obsolete", False),
                    })

    # -- Build vocab_index ----------------------------------------------------
    vocab_index = {}
    for term, entries in term_map.items():
        cat_ids   = [e["category_id"] for e in entries]
        class_ids = list(set(e["class_id"] for e in entries))
        vocab_index[term] = {
            "categories":         cat_ids,
            "roget_class_ids":    class_ids,
            "is_polysemous":      len(cat_ids) > 1,
            "is_modern_addition": any(e["is_modern"] for e in entries),
            "is_obsolete":        any(e["is_obsolete"] for e in entries),
        }

    # -- Build vocab_flat -----------------------------------------------------
    # For polysemous terms, primary = the first (lowest-numbered) category
    vocab_flat = []
    for term, entries in sorted(term_map.items()):
        primary = entries[0]
        colour  = ROGET_CLASS_BASE_COLOURS.get(primary["class_id"], "#888888")
        vocab_flat.append({
            "term":                  term,
            "primary_category_id":   primary["category_id"],
            "primary_category_name": primary["category_name"],
            "primary_section_name":  primary["section_name"],
            "primary_class_id":      primary["class_id"],
            "primary_class_name":    primary["class_name"],
            "all_category_ids":      list(dict.fromkeys(e["category_id"] for e in entries)),
            "is_polysemous":         len(entries) > 1,
            "is_modern_addition":    any(e["is_modern"] for e in entries),
            "is_obsolete":           all(e["is_obsolete"] for e in entries),
            "colour":                colour,
        })

    # -- Build category_colours -----------------------------------------------
    category_colours = {}
    for cls in data["classes"]:
        base = ROGET_CLASS_BASE_COLOURS.get(cls["id"], "#888888")
        category_colours[f"class_{cls['id']}"] = base
        for sec in cls["sections"]:
            # Section colour: base colour (section-level tints deferred to Phase 4)
            category_colours[f"section_{sec['id']}"] = base
            for cat in sec["categories"]:
                category_colours[f"cat_{cat['id']}"] = base

    # -- Write outputs ---------------------------------------------------------
    for path, obj in [(INDEX_FILE, vocab_index), (FLAT_FILE, vocab_flat), (COLOUR_FILE, category_colours)]:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        print(f"Wrote: {path}")

    total    = len(vocab_flat)
    poly     = sum(1 for v in vocab_flat if v["is_polysemous"])
    modern   = sum(1 for v in vocab_flat if v["is_modern_addition"])
    obsolete = sum(1 for v in vocab_flat if v["is_obsolete"])

    print(f"\nVocabulary index summary:")
    print(f"  Total unique terms:  {total:,}")
    print(f"  Polysemous terms:    {poly:,} ({100*poly//max(total,1)}%)")
    print(f"  Modern additions:    {modern:,}")
    print(f"  Obsolete (kept):     {obsolete:,}")
    print()
    print(f"  By Roget class:")
    for cls_id, cls_name in ROGET_CLASSES.items():
        count = sum(1 for v in vocab_flat if v["primary_class_id"] == cls_id)
        print(f"    Class {cls_id} ({cls_name}): {count:,} terms")


if __name__ == "__main__":
    main()
