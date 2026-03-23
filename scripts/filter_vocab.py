"""
filter_vocab.py
Apply the filter cascade to raw Roget vocabulary.

Filter cascade (in order):
  1. Lowercase all terms
  2. Remove terms shorter than VOCAB_MIN_TERM_LENGTH (4 chars)
  3. Remove terms containing digits
  4. Remove terms containing non-ASCII characters
     (except hyphens in compound words — keep those, strip the hyphen)
  5. Remove proper nouns (terms where the original Roget source was
     capitalized AND the term is not a common English word)
     Strategy: flag terms that are Title-Cased in the source as
     potential proper nouns. Log them for manual review.
     Do NOT silently delete — mark as flagged_proper_noun.
  6. Mark obsolete terms (terms that appeared with | or [obs] or
     [Obs.] in the source). Keep them but mark obsolete: true.
  7. Deduplicate within each category (same lowercased term appearing
     twice in one category's word list)

Output: data/roget/roget_filtered.json
Schema: same as roget_parsed.json, with additions per word:
  Each "words" list becomes a list of objects:
  {
    "term":               string (lowercased),
    "original":           string (as found in source),
    "obsolete":           bool,
    "flagged_proper_noun": bool,
    "kept":               bool  (false = filtered out)
  }

Also output: data/roget/filter_report.json
  Summary of how many terms were filtered at each step, and which
  terms were flagged as potential proper nouns (for manual review).
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
INPUT_FILE     = PROJECT_ROOT / "data" / "roget" / "roget_parsed.json"
OUTPUT_FILE    = PROJECT_ROOT / "data" / "roget" / "roget_filtered.json"
REPORT_FILE    = PROJECT_ROOT / "data" / "roget" / "filter_report.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import VOCAB_MIN_TERM_LENGTH

# Common English words that are title-cased in Roget but are NOT proper nouns.
# Add to this list if the flagged_proper_noun review finds false positives.
COMMON_TITLE_CASED = {
    # Abstract / philosophical concepts capitalised throughout Roget's
    "God", "Nature", "Time", "Man", "Woman", "Truth", "Life", "Death",
    "Earth", "Heaven", "Hell", "World", "State", "Church", "Law",
    "Being", "Good", "Evil", "Fortune", "Justice", "Reason", "Spirit",
    "Soul", "Mind", "Body", "Heart", "Will", "Fate", "Chance",
    # Cardinal directions used as common nouns / adjectives
    "East", "West", "North", "South",
    "Eastern", "Western", "Northern", "Southern",
    # Seasons and times of day used as common nouns
    "Spring", "Summer", "Autumn", "Winter",
    "Morning", "Evening", "Night", "Noon",
    # Institutional / generic terms
    "Crown", "Court", "Parliament", "Senate", "Congress",
    "Army", "Navy", "Fleet", "Press", "Stage", "Market",
}

# Markers that indicate an obsolete term in the Gutenberg text
OBS_MARKERS = re.compile(r'\[obs[.\]]|\[Obs[.\]]|\bobs\b', re.IGNORECASE)

def classify_term(original: str) -> dict:
    """
    Classify a single term from the raw word list.
    Returns a dict with term, original, obsolete, flagged_proper_noun, kept.
    """
    # Detect obsolete markers (strip them for the clean term)
    is_obsolete = bool(OBS_MARKERS.search(original))
    clean = OBS_MARKERS.sub('', original).strip().strip('|').strip()
    lowered = clean.lower()

    # Filter: too short
    if len(lowered) < VOCAB_MIN_TERM_LENGTH:
        return {"term": lowered, "original": original, "obsolete": is_obsolete,
                "flagged_proper_noun": False, "kept": False, "filter_reason": "too_short"}

    # Filter: contains digits
    if re.search(r'\d', lowered):
        return {"term": lowered, "original": original, "obsolete": is_obsolete,
                "flagged_proper_noun": False, "kept": False, "filter_reason": "contains_digit"}

    # Handle hyphens: "well-being" → "wellbeing" for matching purposes
    # Keep the hyphenated form as the term
    normalized = lowered.replace('-', '')
    if not normalized.isalpha():
        return {"term": lowered, "original": original, "obsolete": is_obsolete,
                "flagged_proper_noun": False, "kept": False, "filter_reason": "non_alpha"}

    # Flag potential proper nouns (Title Case in source, not in exception list)
    is_proper = (
        clean[0].isupper()
        and clean not in COMMON_TITLE_CASED
        and not clean.startswith(tuple(COMMON_TITLE_CASED))
    )

    return {
        "term":                lowered,
        "original":            original,
        "obsolete":            is_obsolete,
        "flagged_proper_noun": is_proper,
        "kept":                True,
    }


def process_category(cat: dict) -> tuple[list[dict], dict]:
    """Process a category's word list. Returns (classified_words, stats)."""
    seen: set[str] = set()
    results: list[dict] = []
    stats = {
        "total_raw": 0, "kept": 0, "filtered_short": 0,
        "filtered_digit": 0, "filtered_non_alpha": 0,
        "marked_obsolete": 0, "flagged_proper": 0, "deduplicated": 0,
    }

    for word in cat.get("words", []):
        if not isinstance(word, str) or not word.strip():
            continue
        stats["total_raw"] += 1
        classified = classify_term(word)

        if not classified["kept"]:
            reason = classified.get("filter_reason", "unknown")
            if reason == "too_short":        stats["filtered_short"]     += 1
            elif reason == "contains_digit": stats["filtered_digit"]     += 1
            elif reason == "non_alpha":      stats["filtered_non_alpha"] += 1
            results.append(classified)
            continue

        # Deduplicate within category
        if classified["term"] in seen:
            classified["kept"] = False
            classified["filter_reason"] = "duplicate"
            stats["deduplicated"] += 1
            results.append(classified)
            continue

        seen.add(classified["term"])
        if classified["obsolete"]:            stats["marked_obsolete"] += 1
        if classified["flagged_proper_noun"]: stats["flagged_proper"]  += 1
        stats["kept"] += 1
        results.append(classified)

    return results, stats


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run parse_roget.py first.")
        sys.exit(1)

    print(f"Loading {INPUT_FILE} ...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        parsed = json.load(f)

    global_stats = {
        "total_raw": 0, "kept": 0, "filtered_short": 0,
        "filtered_digit": 0, "filtered_non_alpha": 0,
        "marked_obsolete": 0, "flagged_proper": 0, "deduplicated": 0,
    }
    flagged_proper_nouns: list[dict] = []

    # Process every category in the hierarchy
    for cls in parsed["classes"]:
        for sec in cls["sections"]:
            for cat in sec["categories"]:
                classified, stats = process_category(cat)
                cat["words"] = classified  # Replace raw list with classified list
                for k in global_stats:
                    global_stats[k] += stats.get(k, 0)
                # Collect flagged proper nouns for review
                for w in classified:
                    if w.get("flagged_proper_noun") and w.get("kept"):
                        flagged_proper_nouns.append({
                            "term": w["term"],
                            "original": w["original"],
                            "category_id": cat["id"],
                            "category_name": cat["name"],
                        })

    # Update meta
    parsed["meta"]["filter_timestamp"] = datetime.now(timezone.utc).isoformat()
    parsed["meta"]["kept_words"] = global_stats["kept"]

    # Write filtered output
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    print(f"Wrote: {OUTPUT_FILE}")

    # Write report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "global_stats": global_stats,
        "flagged_proper_noun_count": len(flagged_proper_nouns),
        "flagged_proper_nouns": flagged_proper_nouns,
    }
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Wrote: {REPORT_FILE}")

    print(f"\nFilter results:")
    print(f"  Raw terms:            {global_stats['total_raw']:,}")
    print(f"  Kept:                 {global_stats['kept']:,}")
    print(f"  Filtered (short):     {global_stats['filtered_short']:,}")
    print(f"  Filtered (digits):    {global_stats['filtered_digit']:,}")
    print(f"  Filtered (non-alpha): {global_stats['filtered_non_alpha']:,}")
    print(f"  Marked obsolete:      {global_stats['marked_obsolete']:,}")
    print(f"  Flagged proper noun:  {global_stats['flagged_proper']:,}")
    print(f"  Deduplicated:         {global_stats['deduplicated']:,}")
    print(f"\nReview flagged proper nouns in: {REPORT_FILE}")
    print("Add false positives to COMMON_TITLE_CASED in filter_vocab.py and re-run.")


if __name__ == "__main__":
    main()
