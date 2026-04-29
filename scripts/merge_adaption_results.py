"""
merge_adaption_results.py
Merge Adaption enhanced_completion descriptions back into:
  1. backend/data/journal/journal.json
  2. kaggle_export/discoveries.parquet

Usage:
    py -3.12 scripts/merge_adaption_results.py --input <adaption_output.json>
    py -3.12 scripts/merge_adaption_results.py --input kaggle_export/adaption_result.json --dry-run
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print("pandas not installed. Run: py -3.12 -m pip install pandas pyarrow")
    sys.exit(1)

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
JOURNAL_PATH   = PROJECT_ROOT / "backend" / "data" / "journal" / "journal.json"
DISCOVERIES_IN = PROJECT_ROOT / "kaggle_export" / "discoveries.parquet"


# ── Text cleaner ─────────────────────────────────────────────────────────────

def clean_description(raw) -> str:
    """
    Clean an Adaption enhanced_completion:
      - Fix mojibake (UTF-8 read as Latin-1)
      - Unescape HTML entities
      - Strip markdown bold
      - Normalize whitespace
    """
    if not raw or (isinstance(raw, float)):
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Fix mojibake
    try:
        text = text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    # HTML entities
    text = html.unescape(text)
    # Markdown bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\\([*_])', r'\1', text)
    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Build lookup from Adaption output ────────────────────────────────────────

def build_lookup(adaption_data: list) -> dict:
    """
    Build two lookup dicts from Adaption output:
      - by_id:   { id -> description }
      - by_pair: { (term_a, term_b) -> description }
    """
    by_id   = {}
    by_pair = {}

    for item in adaption_data:
        desc = clean_description(item.get("enhanced_completion", ""))
        if not desc:
            continue

        entry_id = item.get("id", "")
        ta = str(item.get("term_a", "")).strip().lower()
        tb = str(item.get("term_b", "")).strip().lower()

        if entry_id:
            by_id[entry_id] = desc
        if ta and tb:
            by_pair[(ta, tb)] = desc
            by_pair[(tb, ta)] = desc  # bidirectional

    return by_id, by_pair


# ── Merge into journal.json ───────────────────────────────────────────────────

def merge_journal(by_id: dict, by_pair: dict, dry_run: bool) -> tuple[int, int]:
    """
    Merge descriptions into journal.json.
    Returns (matched_by_id, matched_by_pair).
    """
    if not JOURNAL_PATH.exists():
        print(f"  Journal not found: {JOURNAL_PATH}")
        return 0, 0

    with open(JOURNAL_PATH, encoding="utf-8") as f:
        journal = json.load(f)

    matched_id   = 0
    matched_pair = 0
    skipped      = 0

    for entry in journal:
        if entry.get("type") != "probe_discovery":
            continue

        # Skip if already has a clean description
        existing = entry.get("generated_description", "")
        if existing and "&#" not in str(existing) and "**" not in str(existing):
            skipped += 1
            continue

        desc = None

        # Try by ID first
        entry_id = entry.get("id", "")
        if entry_id and entry_id in by_id:
            desc = by_id[entry_id]
            matched_id += 1

        # Fall back to term pair
        if not desc:
            notes = str(entry.get("user_notes", ""))
            m = re.match(r'^(.+?)\s+vs\s+(.+)$', notes)
            if m:
                ta = m.group(1).strip().lower()
                tb = m.group(2).strip().lower()
                if (ta, tb) in by_pair:
                    desc = by_pair[(ta, tb)]
                    matched_pair += 1

        if desc:
            entry["generated_description"] = desc

    total_matched = matched_id + matched_pair
    print(f"  Journal: {len(journal)} entries")
    print(f"    Matched by ID:   {matched_id}")
    print(f"    Matched by pair: {matched_pair}")
    print(f"    Total matched:   {total_matched}")
    print(f"    Already had desc: {skipped}")
    print(f"    Unmatched:       {len([e for e in journal if e.get('type')=='probe_discovery']) - total_matched - skipped}")

    if not dry_run:
        with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
            json.dump(journal, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {JOURNAL_PATH}")
    else:
        print("  [DRY RUN] Journal not written.")

    return matched_id, matched_pair


# ── Merge into discoveries.parquet ───────────────────────────────────────────

def merge_parquet(by_id: dict, by_pair: dict, dry_run: bool,
                  output_path: Path) -> int:
    """
    Merge descriptions into discoveries.parquet.
    Returns number of rows updated.
    """
    if not DISCOVERIES_IN.exists():
        print(f"  Discoveries parquet not found: {DISCOVERIES_IN}")
        return 0

    df = pd.read_parquet(DISCOVERIES_IN)
    print(f"  Parquet: {len(df)} rows")

    updated = 0

    def get_desc(row):
        nonlocal updated
        # Try by ID
        if row.get("id", "") in by_id:
            updated += 1
            return by_id[row["id"]]
        # Try by pair
        ta = str(row.get("term_a", "")).strip().lower()
        tb = str(row.get("term_b", "")).strip().lower()
        if (ta, tb) in by_pair:
            updated += 1
            return by_pair[(ta, tb)]
        # Keep existing
        return row.get("generated_description", "")

    df["generated_description"] = df.apply(get_desc, axis=1)

    # Reset updated counter (apply runs twice in some pandas versions)
    # Re-count properly
    updated = 0
    for _, row in df.iterrows():
        ta = str(row.get("term_a", "")).strip().lower()
        tb = str(row.get("term_b", "")).strip().lower()
        if row.get("id", "") in by_id or (ta, tb) in by_pair:
            updated += 1

    print(f"    Updated: {updated}")
    print(f"    With descriptions: {df.generated_description.notna().sum()}")

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        print(f"  Saved: {output_path}")
    else:
        print(f"  [DRY RUN] Parquet not written.")

    return updated


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Merge Adaption enhanced_completion back into journal and Kaggle dataset."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Adaption output JSON file"
    )
    parser.add_argument(
        "--output", "-o",
        default="kaggle_export/discoveries.parquet",
        help="Output discoveries parquet (default: kaggle_export/discoveries.parquet)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing any files"
    )
    parser.add_argument(
        "--skip-journal",
        action="store_true",
        help="Only update the parquet, skip journal.json"
    )
    parser.add_argument(
        "--skip-parquet",
        action="store_true",
        help="Only update journal.json, skip parquet"
    )
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    print(f"Loading Adaption output: {input_path}")
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)
    print(f"  {len(data)} rows loaded")

    # Verify structure
    if not data or "enhanced_completion" not in data[0]:
        print("ERROR: JSON does not contain 'enhanced_completion' field.")
        print(f"  Available keys: {list(data[0].keys()) if data else 'empty'}")
        sys.exit(1)

    # Build lookup
    print()
    print("Building lookup tables...")
    by_id, by_pair = build_lookup(data)
    with_desc = sum(1 for item in data if item.get("enhanced_completion"))
    print(f"  Rows with descriptions: {with_desc} / {len(data)}")
    print(f"  Lookup by ID:   {len(by_id)} entries")
    print(f"  Lookup by pair: {len(by_pair) // 2} pairs (bidirectional)")

    if args.dry_run:
        print()
        print("=== DRY RUN MODE — no files will be written ===")

    # Sample output
    print()
    print("Sample descriptions (first 5):")
    count = 0
    for item in data:
        desc = clean_description(item.get("enhanced_completion", ""))
        if desc:
            ta = item.get("term_a", "")
            tb = item.get("term_b", "")
            print(f"  {ta} vs {tb}")
            print(f"    {desc[:150]}...")
            print()
            count += 1
            if count >= 5:
                break

    # Merge journal
    if not args.skip_journal:
        print("=" * 50)
        print("Merging into journal.json...")
        merge_journal(by_id, by_pair, args.dry_run)

    # Merge parquet
    if not args.skip_parquet:
        print()
        print("=" * 50)
        print("Merging into discoveries.parquet...")
        merge_parquet(by_id, by_pair, args.dry_run, output_path)

    print()
    print("Done.")
    if args.dry_run:
        print("Re-run without --dry-run to write changes.")


if __name__ == "__main__":
    main()