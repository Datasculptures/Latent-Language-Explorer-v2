"""
migrate_v1_journal.py
Migrate V1 field journal (localStorage JSON export) to V2 journal format.

Usage:
    py scripts/migrate_v1_journal.py --input path/to/v1_journal.json \
                                     --output backend/data/journal/journal.json \
                                     [--dry-run] [--force] [--verbose]

V1 schema per entry:
    { id, timestamp, x, y, desert_value, note, nearest_concepts[] }

What is migrated:
    coordinates_2d      ← [x, y] from V1
    desert_value        ← direct
    user_notes          ← from V1 "note" field
    nearest_concepts    ← carried forward; roget fields set to null
    v1_source           ← original V1 entry preserved verbatim

What cannot be backfilled (set to null):
    coordinates_highD   V1 did not store high-dimensional vectors
    roget_context       V1 had no Roget taxonomy

All migrated entries have type: "v1_import".
"""
import argparse
import json
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    MAX_CONCEPT_LABEL_LENGTH, MAX_USER_NOTE_LENGTH,
    MAX_TAGS_PER_ENTRY, SCHEMA_VERSION,
)

JOURNAL_DIR = PROJECT_ROOT / "backend" / "data" / "journal"


def _sanitize(s: str, max_len: int = 500) -> str:
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', str(s))
    s = s.replace('<', '&lt;').replace('>', '&gt;')
    return s.strip()[:max_len]


def migrate_entry(v1: dict, verbose: bool = False) -> dict | None:
    try:
        entry_id = str(v1.get('id', uuid.uuid4()))
        if len(entry_id) > 36:
            entry_id = str(uuid.uuid4())

        timestamp = v1.get('timestamp') or datetime.now(timezone.utc).isoformat()

        x = float(v1.get('x', 0.0))
        y = float(v1.get('y', 0.0))
        desert_value = max(0.0, float(v1.get('desert_value', 0.0)))
        note = _sanitize(v1.get('note', ''), MAX_USER_NOTE_LENGTH)

        nearest = []
        for c in (v1.get('nearest_concepts') or [])[:10]:
            if isinstance(c, dict):
                nearest.append({
                    "term":             _sanitize(c.get('term', ''), MAX_CONCEPT_LABEL_LENGTH),
                    "distance":         float(c.get('distance', 0.0)),
                    "roget_categories": None,
                    "roget_class":      None,
                })

        return {
            "id":                    entry_id,
            "timestamp":             timestamp,
            "type":                  "v1_import",
            "coordinates_2d":        [x, y],
            "coordinates_highD":     None,
            "desert_value":          desert_value,
            "nearest_concepts":      nearest,
            "roget_context":         None,
            "generated_description": None,
            "user_notes":            note,
            "fabrication_notes": {
                "material": "", "method": "", "dimensions": "",
                "status": "idea", "photos": [],
            },
            "tags":           [],
            "starred":        False,
            "v1_source":      v1,
            "schema_version": SCHEMA_VERSION,
        }
    except Exception as e:
        if verbose:
            print(f"  [SKIP] {v1.get('id', '?')}: {e}")
        return None


def load_v1_journal(path: Path) -> list[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and 'entries' in data:
        return data['entries']
    raise ValueError("Cannot parse V1 journal: expected array or {entries: [...]}")


def atomic_write(output: Path, entries: list[dict]):
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=output.parent, suffix=".tmp")
    try:
        with open(fd, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2, default=str)
        Path(tmp).replace(output)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Migrate V1 field journal to V2 format."
    )
    parser.add_argument('--input',   required=True, help="Path to V1 journal JSON.")
    parser.add_argument('--output',  required=True, help="Output path for V2 journal.json.")
    parser.add_argument('--dry-run', action='store_true', help="Validate without writing.")
    parser.add_argument('--force',   action='store_true', help="Overwrite existing output.")
    parser.add_argument('--verbose', action='store_true', help="Print per-entry results.")
    args = parser.parse_args()

    input_path  = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    # Security: output must stay within JOURNAL_DIR
    if not str(output_path).startswith(str(JOURNAL_DIR.resolve())):
        print(f"ERROR: Output must be within {JOURNAL_DIR}")
        sys.exit(1)

    if not input_path.exists():
        print(f"ERROR: Input not found: {input_path}")
        sys.exit(1)

    if output_path.exists() and not args.force and not args.dry_run:
        print(f"ERROR: Output exists: {output_path}")
        print("Use --force to overwrite or --dry-run to validate only.")
        sys.exit(1)

    print(f"Loading V1 journal: {input_path}")
    try:
        v1_entries = load_v1_journal(input_path)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Found {len(v1_entries)} V1 entries.")

    migrated, skipped = [], 0
    for e in v1_entries:
        result = migrate_entry(e, verbose=args.verbose)
        if result is not None:
            migrated.append(result)
            if args.verbose:
                print(f"  [OK] {result['id']} desert={result['desert_value']:.4f}")
        else:
            skipped += 1

    print(f"\nMigration summary:")
    print(f"  Input entries:    {len(v1_entries)}")
    print(f"  Migrated:         {len(migrated)}")
    print(f"  Skipped (errors): {skipped}")
    print(f"  roget_context:    null on all entries (cannot be backfilled)")
    print(f"  coordinates_highD: null on all entries (V1 did not store high-D vectors)")
    print(f"  v1_source:        original V1 data preserved in each entry")

    if args.dry_run:
        print("\nDry run complete — no files written.")
        return

    atomic_write(output_path, migrated)
    print(f"\nWrote {len(migrated)} entries → {output_path}")


if __name__ == "__main__":
    main()
