"""
discovery_report.py
Summarise all discovery runs and write a machine-readable report.

Loads every discoveries_*.json file in data/discovery/, deduplicates
by (term_a, term_b) pair, and prints a comparison table.

Writes: data/discovery/discovery_report.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
DISCOVERY_DIR = PROJECT_ROOT / "data" / "discovery"
JOURNAL_FILE  = PROJECT_ROOT / "backend" / "data" / "journal" / "journal.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import PROBE_DESERT_GATE_THRESHOLD, PROBE_DESERT_SHALLOW_THRESHOLD


def load_journal() -> list[dict]:
    """Load all probe_discovery entries from the field journal."""
    if not JOURNAL_FILE.exists():
        return []
    with open(JOURNAL_FILE, encoding="utf-8") as fh:
        journal = json.load(fh)
    return [e for e in journal if e.get("type") == "probe_discovery"]


def main():
    journal = load_journal()
    all_journal = []
    if JOURNAL_FILE.exists():
        with open(JOURNAL_FILE, encoding="utf-8") as fh:
            all_journal = json.load(fh)

    if not journal:
        print("No probe_discovery entries found in journal.")
        sys.exit(1)

    total_probed  = len(journal)
    deep_entries  = [e for e in journal
                     if e.get("desert_value", 0) >= PROBE_DESERT_SHALLOW_THRESHOLD]
    shallow_entries = [e for e in journal
                       if PROBE_DESERT_GATE_THRESHOLD <= e.get("desert_value", 0)
                       < PROBE_DESERT_SHALLOW_THRESHOLD]

    deep_count    = len(deep_entries)
    shallow_count = len(shallow_entries)
    journal_count = len(all_journal)

    entries_sorted = sorted(journal, key=lambda e: e.get("desert_value", 0), reverse=True)
    v2_max_desert  = entries_sorted[0].get("desert_value", 0) if entries_sorted else 0
    top5 = entries_sorted[:5]

    # Level breakdown from tags
    level_counts: dict[str, int] = {}
    for e in journal:
        for tag in e.get("tags", []):
            if tag in ("cross_class", "cross_section", "adjacent_cat"):
                level_counts[tag] = level_counts.get(tag, 0) + 1
                break

    # Print report
    print("=" * 60)
    print("LATENT LANGUAGE EXPLORER V2 -- DISCOVERY REPORT")
    print("=" * 60)
    print()
    print(f"Total probed:       {total_probed}")
    print(f"Deep (>= {PROBE_DESERT_SHALLOW_THRESHOLD:.2f}):       {deep_count}")
    print(f"Shallow:            {shallow_count}")
    print(f"Max desert depth:   {v2_max_desert:.4f}")
    print(f"Journal entries:    {journal_count}")
    print()
    if level_counts:
        print("By level (from tags):")
        for lv, n in sorted(level_counts.items()):
            print(f"  {lv:<20} {n}")
        print()
    print("Top 5 discoveries:")
    print(f"  {'pair':<46} {'depth':>7}  deepest_near")
    print("  " + "-" * 70)
    for e in top5:
        notes = e.get("user_notes", "")
        near  = e.get("nearest_concepts", [{}])[0].get("term", "?") \
                if e.get("nearest_concepts") else "?"
        print(
            f"  {notes:<46} "
            f"{e.get('desert_value', 0):>7.4f}  {near}"
        )

    # Write machine-readable report
    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "total_probed":      total_probed,
        "deep_count":        deep_count,
        "shallow_count":     shallow_count,
        "v2_max_desert":     v2_max_desert,
        "journal_count":     journal_count,
        "level_counts":      level_counts,
        "gate_threshold":    PROBE_DESERT_GATE_THRESHOLD,
        "shallow_threshold": PROBE_DESERT_SHALLOW_THRESHOLD,
        "top5": [
            {
                "pair":         e.get("user_notes", ""),
                "desert_value": e.get("desert_value"),
                "deepest_near": e.get("nearest_concepts", [{}])[0].get("term", "?")
                                if e.get("nearest_concepts") else "?",
                "tags":         e.get("tags", []),
            }
            for e in top5
        ],
    }
    out = DISCOVERY_DIR / "discovery_report.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print()
    print(f"Report written: {out}")


if __name__ == "__main__":
    main()
