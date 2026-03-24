"""
batch_cross_discover.py
Run probes on a set of cross-category pairs and record discoveries.

Usage:
  py scripts/batch_cross_discover.py \
     --pairs data/discovery/probe_pairs_cross_class.json \
     [--describe]              Fetch LLM descriptions for deep deserts
     [--journal]               Write discoveries to field journal
     [--min-desert 0.02]       Only record entries above this threshold
     [--top 50]                Only process the top N pairs by distance
     [--dry-run]               Don't call LLM or write journal
     [--yes]                   Skip cost confirmation prompt
     [--api-url http://localhost:8000]
     [--verbose]

Discoveries are sorted by desert_max descending.
LLM calls are gated: only when desert_max >= DESERT_GATE_THRESHOLD.
The LLM is called via /api/describe-point (backend proxy, never directly).
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
BUNDLE_FILE   = PROJECT_ROOT / "backend" / "data" / "data_bundle.json"
BASE_NPZ      = PROJECT_ROOT / "data" / "embeddings" / "base_embeddings.npz"
DISCOVERY_DIR = PROJECT_ROOT / "data" / "discovery"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from probe_lib import EmbeddingIndex, run_probe, probe_result_to_dict
from terrain_config import (
    DESERT_GATE_THRESHOLD, DESERT_SHALLOW_THRESHOLD,
    LLM_RATE_LIMIT_INTERVAL_SECONDS,
)


def fetch_description(
    api_url:          str,
    term_a:           str,
    term_b:           str,
    desert_value:     float,
    nearest_concepts: list[dict],
    roget_context:    dict,
) -> str | None:
    """Call /api/describe-point via the backend proxy. Never calls Anthropic directly."""
    try:
        import urllib.request
        payload = json.dumps({
            "coordinates_2d":    [0.0, 0.0],  # Not available at CLI level
            "desert_value":      desert_value,
            "nearest_concepts": [
                {
                    "term":               c["term"],
                    "distance":           c["distance"],
                    "roget_category_name": c.get("category_name", ""),
                }
                for c in nearest_concepts[:5]
            ],
            "roget_context":     roget_context,
            "shallow_threshold": DESERT_SHALLOW_THRESHOLD,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{api_url}/api/describe-point",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("description")
    except Exception as e:
        print(f"    [describe failed: {e}]")
        return None


def post_journal_entry(api_url: str, entry: dict) -> bool:
    """POST a journal entry to the backend API."""
    try:
        import urllib.request
        payload = json.dumps(entry, default=str).encode("utf-8")
        req = urllib.request.Request(
            f"{api_url}/api/journal",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 201
    except Exception as e:
        print(f"    [journal write failed: {e}]")
        return False


def check_api_health(api_url: str) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"{api_url}/api/health", timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Batch cross-category probe discovery.")
    parser.add_argument("--pairs",      required=True,
                        help="Probe pairs JSON file.")
    parser.add_argument("--describe",   action="store_true",
                        help="Fetch LLM descriptions.")
    parser.add_argument("--journal",    action="store_true",
                        help="Write to field journal.")
    parser.add_argument("--min-desert", type=float, default=DESERT_GATE_THRESHOLD,
                        help=f"Minimum desert_max to record (default: {DESERT_GATE_THRESHOLD})")
    parser.add_argument("--top",        type=int, default=0,
                        help="Process only top N pairs by distance (0 = all).")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Don't call LLM or write journal.")
    parser.add_argument("--yes",        action="store_true",
                        help="Skip cost confirmation prompt.")
    parser.add_argument("--api-url",    default="http://localhost:8000",
                        help="Backend API URL (default: http://localhost:8000)")
    parser.add_argument("--output",     default=None,
                        help="Save results to JSON file.")
    parser.add_argument("--verbose",    action="store_true")
    args = parser.parse_args()

    pairs_path = Path(args.pairs)
    if not pairs_path.exists():
        print(f"ERROR: {pairs_path} not found. Run select_probe_pairs.py first.")
        sys.exit(1)

    # API health check
    if (args.describe or args.journal) and not args.dry_run:
        if not check_api_health(args.api_url):
            print(f"ERROR: Backend not reachable at {args.api_url}")
            print("Start the backend before running with --describe or --journal.")
            sys.exit(1)
        print(f"Backend health: OK ({args.api_url})")

    with open(pairs_path, encoding="utf-8") as f:
        pairs_data = json.load(f)
    pairs = pairs_data["pairs"]

    # Sort by distance descending (deepest conceptual gaps first)
    pairs.sort(key=lambda p: p["distance_highD"], reverse=True)
    if args.top > 0:
        pairs = pairs[:args.top]

    print(f"Pairs to probe: {len(pairs)}")

    # LLM cost estimate
    if args.describe and not args.dry_run:
        print(f"\nLLM cost estimate: up to {len(pairs)} describe-point calls")
        print(f"  (actual calls gated: only when desert_max >= {DESERT_GATE_THRESHOLD})")
        if not args.yes:
            resp = input("Proceed? [y/N] ").strip().lower()
            if resp not in ("y", "yes"):
                print("Aborted.")
                sys.exit(0)

    print("\nBuilding embedding index ...")
    index = EmbeddingIndex()
    index.build(BASE_NPZ, BUNDLE_FILE)

    results = []
    skipped = 0
    t_start = time.time()

    print(f"\nRunning {len(pairs)} probes ...")
    for i, pair in enumerate(pairs):
        ta, tb = pair["term_a"], pair["term_b"]

        result = run_probe(index, ta, tb)
        if result is None:
            if args.verbose:
                print(f"  [{i+1}/{len(pairs)}] SKIP: {ta} vs {tb} (term not in index)")
            skipped += 1
            continue

        entry = probe_result_to_dict(result)
        entry["pair_meta"] = pair

        # LLM description (gated by desert threshold)
        description = None
        if args.describe and not args.dry_run and result.is_deep:
            time.sleep(LLM_RATE_LIMIT_INTERVAL_SECONDS)
            roget_ctx = {
                "category_a": pair.get("category_name_a", ""),
                "category_b": pair.get("category_name_b", ""),
                "class_a":    pair.get("class_name_a", ""),
                "class_b":    pair.get("class_name_b", ""),
                "section_a":  pair.get("section_name_a", ""),
                "section_b":  pair.get("section_name_b", ""),
            }
            description = fetch_description(
                args.api_url, ta, tb,
                result.deepest_step.desert_value,
                result.deepest_step.nearest_concepts,
                roget_ctx,
            )
            entry["generated_description"] = description

        results.append(entry)

        if args.verbose or result.desert_max >= args.min_desert:
            depth_label = (
                "DEEP"    if result.desert_max >= DESERT_SHALLOW_THRESHOLD else
                "shallow" if result.desert_max >= DESERT_GATE_THRESHOLD    else
                "flat"
            )
            desc_preview = f"\n      '{description[:80]}...'" if description else ""
            print(f"  [{i+1}/{len(pairs)}] {ta} vs {tb}")
            print(f"    desert_max={result.desert_max:.4f} [{depth_label}]"
                  f"  deepest_near={result.deepest_step.nearest_term}"
                  f"{desc_preview}")

    results.sort(key=lambda r: r["desert_max"], reverse=True)
    above_threshold = [r for r in results if r["desert_max"] >= args.min_desert]

    # Write to journal
    if args.journal and not args.dry_run:
        print(f"\nWriting {len(above_threshold)} entries to journal ...")
        written = 0
        for r in above_threshold:
            pm = r.get("pair_meta", {})
            roget_ctx = None
            if pm.get("category_id_a") and pm.get("category_id_b"):
                roget_ctx = {
                    "category_a": pm.get("category_name_a", ""),
                    "category_b": pm.get("category_name_b", ""),
                    "section_a":  pm.get("section_name_a", ""),
                    "section_b":  pm.get("section_name_b", ""),
                    "class_a":    pm.get("class_name_a", ""),
                    "class_b":    pm.get("class_name_b", ""),
                }

            journal_entry = {
                "type":               "probe_discovery",
                "coordinates_2d":     [0.0, 0.0],
                "desert_value":       r["desert_max"],
                "nearest_concepts": [
                    {
                        "term":             c["term"],
                        "distance":         c["distance"],
                        "roget_categories": [c.get("category_id")] if c.get("category_id") else None,
                        "roget_class":      c.get("class_name"),
                    }
                    for c in r["deepest_step"].get("nearest_concepts", [])[:5]
                ],
                "roget_context":          roget_ctx,
                "generated_description":  r.get("generated_description"),
                "user_notes":             f"{r['term_a']} vs {r['term_b']}",
                "tags": [
                    f"class_{pm.get('class_id_a', '')}",
                    f"class_{pm.get('class_id_b', '')}",
                    pm.get("level", "cross_class"),
                ],
            }
            if post_journal_entry(args.api_url, journal_entry):
                written += 1
        print(f"  Wrote {written} journal entries.")

    # Save results
    output_path = Path(args.output) if args.output else \
        DISCOVERY_DIR / f"discoveries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "meta": {
            "pair_count":      len(pairs),
            "probed":          len(results),
            "skipped":         skipped,
            "above_threshold": len(above_threshold),
            "min_desert":      args.min_desert,
            "elapsed_seconds": time.time() - t_start,
            "timestamp":       datetime.now(timezone.utc).isoformat(),
        },
        "discoveries": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"Discovery run complete:")
    print(f"  Probed:            {len(results)}")
    print(f"  Skipped:           {skipped}")
    print(f"  Above threshold:   {len(above_threshold)}")
    if results:
        print(f"  Deepest desert:    {results[0]['desert_max']:.4f}")
        print(f"    {results[0]['term_a']} vs {results[0]['term_b']}")
    print(f"  Output:            {output_path}")


if __name__ == "__main__":
    main()
