"""
describe_starred.py
Request LLM descriptions for all starred journal entries that do not yet
have a generated_description.

Usage:
    py scripts/describe_starred.py
    py scripts/describe_starred.py --dry-run
    py scripts/describe_starred.py --limit 5 --verbose
    py scripts/describe_starred.py --yes               (skip y/N prompt)
    py scripts/describe_starred.py --api-url http://localhost:8000

The API key is never in this script. All LLM calls are proxied through
the backend /api/describe-point endpoint.

Results are written incrementally — one PUT per description — so progress
is preserved if the script is interrupted.
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Locate terrain_config for rate-limit constant
# ---------------------------------------------------------------------------

_SCRIPT_DIR  = Path(__file__).parent
_PROJECT_DIR = _SCRIPT_DIR.parent

try:
    sys.path.insert(0, str(_SCRIPT_DIR))
    from terrain_config import LLM_RATE_LIMIT_INTERVAL_SECONDS
except ImportError:
    LLM_RATE_LIMIT_INTERVAL_SECONDS = 3

COST_PER_CALL = 0.0002  # approximate USD per describe-point call

# ---------------------------------------------------------------------------
# HTTP helpers (no third-party deps)
# ---------------------------------------------------------------------------

def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _put(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _http_error_detail(e: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(e.read())
        return body.get("detail", str(e))
    except Exception:
        return str(e)

# ---------------------------------------------------------------------------
# Journal helpers
# ---------------------------------------------------------------------------

def _parse_pair(notes: str) -> tuple[str, str]:
    import re
    m = re.match(r"^(.+?)\s+vs\s+(.+)$", (notes or "").strip(), re.IGNORECASE)
    return (m.group(1).strip(), m.group(2).strip()) if m else (notes or "", "")


def _pair_label(notes: str) -> str:
    a, b = _parse_pair(notes)
    return f"{a} vs {b}" if b else a

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(
    api_url:       str  = "http://localhost:8000",
    dry_run:       bool = False,
    limit:         int  = 0,
    verbose:       bool = False,
    yes:           bool = False,
    describe_all:  bool = False,
) -> int:
    """
    Returns exit code: 0 = success, 1 = error.
    """
    api_url = api_url.rstrip("/")

    # ── Health check ────────────────────────────────────────────────────
    print(f"Checking backend health at {api_url} …")
    try:
        health = _get(f"{api_url}/api/health")
        print(f"  Backend: {health.get('status', '?')} v{health.get('version', '?')}")
    except Exception as e:
        print(f"ERROR: Backend not reachable — {e}")
        print("  Start the backend with: .\\start.ps1  or  ./start.sh")
        return 1

    # ── Load journal (paginate; API caps at 1000 per request) ────────────
    try:
        entries: list = []
        offset = 0
        PAGE = 1000
        while True:
            resp  = _get(f"{api_url}/api/journal?limit={PAGE}&offset={offset}")
            page  = resp.get("entries", [])
            total = resp.get("total", 0)
            entries.extend(page)
            offset += PAGE
            if offset >= total or not page:
                break
    except Exception as e:
        print(f"ERROR: Could not fetch journal — {e}")
        return 1

    # ── Filter: starred + no description (or --all) ──────────────────────
    targets = [
        e for e in entries
        if (describe_all or e.get("starred"))
        and not e.get("generated_description")
        and e.get("nearest_concepts")          # need nearest for the prompt
        and isinstance(e.get("desert_value"), (int, float))
    ]

    if limit > 0:
        targets = targets[:limit]

    total_starred   = sum(1 for e in entries if e.get("starred"))
    total_with_desc = sum(1 for e in entries if e.get("generated_description"))

    print()
    if describe_all:
        print(f"  Mode: --all (ignoring starred flag)")
    print(f"  Total entries:             {len(entries)}")
    print(f"  Starred entries:           {total_starred}")
    print(f"  Already have description:  {total_with_desc}")
    print(f"  Need description:          {len(targets)}")

    if not targets:
        print()
        print("Nothing to do.")
        return 0

    # ── Cost estimate + confirmation ─────────────────────────────────────
    est_cost    = len(targets) * COST_PER_CALL
    est_minutes = (len(targets) * LLM_RATE_LIMIT_INTERVAL_SECONDS) / 60

    print()
    print(f"  Calls to make:  {len(targets)}")
    print(f"  Estimated cost: ~${est_cost:.4f} USD")
    print(f"  Estimated time: ~{est_minutes:.1f} min "
          f"({LLM_RATE_LIMIT_INTERVAL_SECONDS}s between calls)")

    if dry_run:
        print()
        print("DRY RUN — no calls will be made. Entries that would be described:")
        for e in targets:
            pair = _pair_label(e.get("user_notes", ""))
            print(f"  [{e['desert_value']:.4f}]  {pair}")
        return 0

    if not yes:
        print()
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 0

    # ── Run ─────────────────────────────────────────────────────────────
    print()
    n_written = 0
    n_failed  = 0
    n_skipped = 0

    for i, entry in enumerate(targets):
        entry_id = entry["id"]
        pair     = _pair_label(entry.get("user_notes", ""))
        desert   = entry["desert_value"]

        print(f"[{i+1}/{len(targets)}] {pair}  (desert {desert:.4f})", end="  ", flush=True)

        # Build describe-point request
        body = {
            "coordinates_2d":   entry.get("coordinates_2d", [0, 0]),
            "coordinates_highD": entry.get("coordinates_highD"),
            "desert_value":     desert,
            "nearest_concepts": entry.get("nearest_concepts", []),
            "roget_context":    entry.get("roget_context"),
        }

        try:
            result = _post(f"{api_url}/api/describe-point", body)
        except urllib.error.HTTPError as e:
            detail = _http_error_detail(e)
            if e.code == 503:
                print(f"\nFATAL: Backend returned 503 — API key not configured.")
                print("  Set ANTHROPIC_API_KEY in backend/.env and restart the backend.")
                return 1
            if e.code == 422:
                # Below desert threshold — skip silently
                n_skipped += 1
                print("skipped (below threshold)")
                continue
            if e.code == 429:
                print(f"RATE LIMITED — waiting 5s, retrying once …", end=" ", flush=True)
                time.sleep(5)
                try:
                    result = _post(f"{api_url}/api/describe-point", body)
                except Exception as e2:
                    print(f"FAILED on retry ({e2})")
                    n_skipped += 1
                    continue
            else:
                print(f"FAILED ({e.code}: {detail})")
                n_failed += 1
                continue
        except Exception as e:
            print(f"FAILED ({e})")
            n_failed += 1
            continue

        description = result.get("description", "").strip()
        if not description:
            print("SKIPPED (empty description)")
            n_skipped += 1
            continue

        # Write back to journal
        try:
            _put(f"{api_url}/api/journal/{entry_id}",
                 {"generated_description": description})
        except Exception as e:
            print(f"WROTE description but PUT failed — {e}")
            n_failed += 1
        else:
            short = description[:80] + ("…" if len(description) > 80 else "")
            print(f"✓  {short}")
            if verbose:
                print(f"       {description}")
            n_written += 1

        # Rate limit
        if i < len(targets) - 1:
            time.sleep(LLM_RATE_LIMIT_INTERVAL_SECONDS)

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    print("─" * 50)
    print(f"  Descriptions written: {n_written}")
    print(f"  Failed:               {n_failed}")
    print(f"  Skipped:              {n_skipped}")
    print("─" * 50)

    return 0 if n_failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Request LLM descriptions for starred journal entries.",
    )
    parser.add_argument("--api-url",  default="http://localhost:8000",
                        help="Backend base URL (default: http://localhost:8000)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Print what would be described without calling the API")
    parser.add_argument("--limit",    type=int, default=0,
                        help="Maximum entries to process (default: all)")
    parser.add_argument("--verbose",  action="store_true",
                        help="Print full descriptions, not just the first 80 chars")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip the y/N confirmation prompt")
    parser.add_argument("--all", dest="describe_all", action="store_true",
                        help="Describe all entries without a description (ignore starred flag)")
    args = parser.parse_args()

    sys.exit(run(
        api_url       = args.api_url,
        dry_run       = args.dry_run,
        limit         = args.limit,
        verbose       = args.verbose,
        yes           = args.yes,
        describe_all  = args.describe_all,
    ))


if __name__ == "__main__":
    main()
