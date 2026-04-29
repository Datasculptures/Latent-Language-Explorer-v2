"""
select_probe_pairs.py
Select concept pairs for cross-category probing.

Hierarchy-aware pair selection from the Roget taxonomy.
Outputs a list of (term_a, term_b, level, category_a, category_b,
class_a, class_b) pairs ready for probe_lib.run_probe().

Usage:
  py scripts/select_probe_pairs.py \
     --level cross_class \
     --pairs-per-category 3 \
     --output data/discovery/probe_pairs_cross_class.json \
     [--max-pairs 500] \
     [--verbose]

Levels:
  cross_class    Pairs from different Roget classes (deepest gaps expected)
  cross_section  Pairs from different sections, same class
  adjacent_cat   Pairs from different categories, same section
  all            All three levels

Output schema:
[
  {
    "term_a": str, "term_b": str,
    "level": "cross_class" | "cross_section" | "adjacent_cat",
    "category_id_a": str, "category_id_b": str,
    "section_id_a": str, "section_id_b": str,
    "class_id_a": int, "class_id_b": int,
    "percentile": int,        # 40, 60, or 75
    "distance_highD": float,  # L2 distance in 384d space
    "cosine_sim": float,
  }
]
"""

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
BUNDLE_FILE   = PROJECT_ROOT / "backend" / "data" / "data_bundle.json"
BASE_NPZ      = PROJECT_ROOT / "data" / "embeddings" / "base_embeddings.npz"
DISCOVERY_DIR = PROJECT_ROOT / "data" / "discovery"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    PROBE_PERCENTILE_LOW, PROBE_PERCENTILE_HIGH,
    SYNONYM_FILTER_COSINE,
    UMAP_RANDOM_SEED,
    PROBE_MIN_DENSITY_THRESHOLD,
    PROBE_MIN_ZIPF_FREQUENCY,
    PROBE_TERM_BLOCKLIST,
)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def l2_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def morphological_variants(term_a: str, term_b: str) -> bool:
    """
    True if the two terms are likely morphological variants of each other.
    Simple heuristic: one is a prefix of the other with len >= 4 shared chars.
    """
    a, b = term_a.lower(), term_b.lower()
    min_len = min(len(a), len(b))
    if min_len < 4:
        return False
    shared = min_len - 2
    return a[:shared] == b[:shared]


def shared_neighbourhood_score(
    va:       np.ndarray,
    vb:       np.ndarray,
    all_vecs: np.ndarray,
    k:        int = 20,
) -> float:
    """
    Fraction of the top-k neighbours of va that are also in the
    top-k neighbours of vb. A score > 0 means the two terms
    share conceptual neighbourhood even at moderate distance.
    Score = 0 means the terms point in completely different
    directions with no shared vicinity.
    """
    from scipy.spatial import cKDTree
    tree = cKDTree(all_vecs)
    _, idx_a = tree.query(va.reshape(1, -1), k=k + 1)
    _, idx_b = tree.query(vb.reshape(1, -1), k=k + 1)
    set_a = set(idx_a[0][1:])   # exclude self
    set_b = set(idx_b[0][1:])
    overlap = len(set_a & set_b)
    return overlap / k


def select_pairs_from_groups(
    group_a:         list[tuple[str, np.ndarray]],
    group_b:         list[tuple[str, np.ndarray]],
    meta_a:          dict,
    meta_b:          dict,
    level:           str,
    pairs_per_group: int = 3,
    rng:             random.Random = None,
    verbose:         bool = False,
) -> list[dict]:
    """
    Select concept pairs between two groups at 40th, 60th, 75th percentile
    of pairwise L2 distance. Filters synonyms and morphological variants.
    Applies a shared-neighbourhood filter to prefer pairs that have at
    least one common neighbour in their top-20 — a minimal semantic bridge.
    """
    if not group_a or not group_b:
        return []

    MAX_SAMPLE = 80
    if rng is None:
        rng = random.Random(UMAP_RANDOM_SEED)
    sample_a = rng.sample(group_a, min(MAX_SAMPLE, len(group_a)))
    sample_b = rng.sample(group_b, min(MAX_SAMPLE, len(group_b)))

    pairs_with_dist = []
    for ta, va in sample_a:
        for tb, vb in sample_b:
            if ta == tb:
                continue
            if morphological_variants(ta, tb):
                continue
            cs = cosine_sim(va, vb)
            if cs > SYNONYM_FILTER_COSINE:
                continue
            d = l2_distance(va, vb)
            pairs_with_dist.append((ta, tb, d, cs))

    if not pairs_with_dist:
        return []

    pairs_with_dist.sort(key=lambda x: x[2])

    # Build all-vectors array for neighbourhood computation.
    # Only pairs that passed the cosine/distance filters reach here.
    vec_lookup = {t: v for t, v in sample_a + sample_b}
    all_vecs_combined = np.array(list(vec_lookup.values()), dtype=np.float32)

    # Filter: keep pairs with some shared neighbourhood
    # (score > 0 means at least one common neighbour in top-20).
    MIN_SHARED_SCORE = 0.0
    filtered_pairs = []
    for ta, tb, d, cs in pairs_with_dist:
        va_vec = vec_lookup[ta]
        vb_vec = vec_lookup[tb]
        score = shared_neighbourhood_score(va_vec, vb_vec, all_vecs_combined)
        if score > MIN_SHARED_SCORE:
            filtered_pairs.append((ta, tb, d, cs, score))

    if not filtered_pairs:
        # Fall back to unfiltered if nothing shares neighbourhood
        filtered_pairs = [(ta, tb, d, cs, 0.0) for ta, tb, d, cs in pairs_with_dist]

    # Sort filtered pairs by distance for percentile selection
    filtered_pairs.sort(key=lambda x: x[2])
    n = len(filtered_pairs)

    selected = []
    for pct in [PROBE_PERCENTILE_LOW, 60, PROBE_PERCENTILE_HIGH]:
        idx = int(n * pct / 100)
        idx = max(0, min(idx, n - 1))
        ta, tb, d, cs, score = filtered_pairs[idx]
        selected.append({
            "term_a":          ta,
            "term_b":          tb,
            "level":           level,
            "category_id_a":   meta_a.get("category_id"),
            "category_id_b":   meta_b.get("category_id"),
            "category_name_a": meta_a.get("category_name"),
            "category_name_b": meta_b.get("category_name"),
            "section_id_a":    meta_a.get("section_id"),
            "section_id_b":    meta_b.get("section_id"),
            "class_id_a":      meta_a.get("class_id"),
            "class_id_b":      meta_b.get("class_id"),
            "class_name_a":    meta_a.get("class_name"),
            "class_name_b":    meta_b.get("class_name"),
            "percentile":      pct,
            "distance_highD":  d,
            "cosine_sim":      cs,
        })

    return selected[:pairs_per_group]


def build_density_filter(
    emb_map:   dict,
    threshold: float,
    k:         int = 5,
) -> set:
    """
    Return the set of terms that pass the density filter.
    A term passes if its mean distance to its k nearest neighbours
    is below threshold. Sparse/isolated terms are excluded.
    Uses a KD-tree for efficient batch computation.
    """
    from scipy.spatial import cKDTree
    terms_list = list(emb_map.keys())
    matrix     = np.array([emb_map[t] for t in terms_list], dtype=np.float32)

    print(f"Building density filter (k={k}, threshold={threshold}) "
          f"over {len(terms_list):,} terms ...")
    tree       = cKDTree(matrix)
    # Query k+1 to exclude the term itself (distance=0)
    dists, _   = tree.query(matrix, k=k + 1, workers=-1)
    # dists[:,0] is always 0 (self), use dists[:,1:k+1]
    mean_dists = dists[:, 1:k + 1].mean(axis=1)

    dense_terms = {
        terms_list[i]
        for i, d in enumerate(mean_dists)
        if d <= threshold
    }
    sparse_count = len(terms_list) - len(dense_terms)
    print(f"  Dense terms (pass): {len(dense_terms):,}")
    print(f"  Sparse terms (filtered): {sparse_count:,}")
    if sparse_count > 0:
        sparse_sample = [
            terms_list[i] for i, d in enumerate(mean_dists)
            if d > threshold
        ][:10]
        print(f"  Sample filtered: {sparse_sample}")
    return dense_terms


def main():
    parser = argparse.ArgumentParser(
        description="Select probe pairs for cross-category discovery."
    )
    parser.add_argument(
        "--level", default="cross_class",
        choices=["cross_class", "cross_section", "adjacent_cat", "all"],
    )
    parser.add_argument(
        "--pairs-per-category", type=int, default=3,
        help="Pairs to select per category pair (default: 3)",
    )
    parser.add_argument(
        "--max-pairs", type=int, default=1000,
        help="Maximum total pairs output (default: 1000)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path (default: data/discovery/probe_pairs_{level}.json)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    for f in [BUNDLE_FILE, BASE_NPZ]:
        if not f.exists():
            print(f"ERROR: {f} not found.")
            sys.exit(1)

    DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)

    output_path = Path(args.output) if args.output else \
        DISCOVERY_DIR / f"probe_pairs_{args.level}.json"

    print("Loading bundle taxonomy ...")
    with open(BUNDLE_FILE, encoding="utf-8") as f:
        bundle = json.load(f)
    concepts = bundle["concepts"]

    print("Loading embeddings ...")
    emb_data   = np.load(BASE_NPZ, allow_pickle=True)
    emb_terms  = list(emb_data["terms"])
    emb_matrix = emb_data["embeddings"].astype(np.float32)
    emb_map    = {t: emb_matrix[i] for i, t in enumerate(emb_terms)}

    print("Indexing taxonomy ...")
    cat_map:  dict[str, list] = {}
    sec_map:  dict[str, list] = {}
    cls_map:  dict[int, list] = {}
    cat_meta: dict[str, dict] = {}
    sec_meta: dict[str, dict] = {}

    # Filter terms with near-zero norm (poorly represented in model)
    # After normalization, all norms should be ~1.0; terms below 0.5 are suspect
    emb_map = {
        t: v for t, v in emb_map.items()
        if np.linalg.norm(v) >= 0.5
    }
    print(f"After norm filter: {len(emb_map):,} terms")

    # Hyphen filter: exclude compound terms like "back-stairs", "lamb-like".
    # These are Roget-specific; they pass zipf but aren't clean concept words.
    before_hyph = len(emb_map)
    emb_map = {t: v for t, v in emb_map.items() if "-" not in t and "_" not in t}
    print(f"After hyphen filter: {len(emb_map):,} terms ({before_hyph - len(emb_map):,} filtered)")

    # Word frequency filter: exclude archaic/technical terms not found
    # in common English text. Zipf < threshold means the word is too
    # rare to represent a concept a human would recognise as a probe
    # endpoint. This uses an external reference corpus (wordfreq), not
    # the Roget index itself, so archaic terms that cluster with other
    # archaic terms are correctly filtered.
    #
    # When wordfreq is available, skip the density filter below: both
    # filters remove rare/poorly-embedded terms, but their thresholds
    # are calibrated for different vocabulary sizes. Applying both
    # double-filters and removes legitimate common words.
    zipf_active = False
    try:
        from wordfreq import zipf_frequency
        before = len(emb_map)
        emb_map = {
            t: v for t, v in emb_map.items()
            if zipf_frequency(t, "en") >= PROBE_MIN_ZIPF_FREQUENCY
        }
        print(f"After zipf filter (>={PROBE_MIN_ZIPF_FREQUENCY}): "
              f"{len(emb_map):,} terms ({before - len(emb_map):,} filtered)")
        zipf_active = True
    except ImportError:
        print("WARNING: wordfreq not installed -- falling back to density filter. "
              "Run: pip install wordfreq")

    if zipf_active:
        # Zipf already filtered rare/archaic terms; density filter is redundant
        # and would remove legitimate common words (their mean-5-NN distances
        # are higher when archaic neighbours are absent).
        dense_terms = set(emb_map.keys())
        print(f"Density filter skipped (zipf active): {len(dense_terms):,} terms eligible")
    else:
        # Fallback: density filter as proxy for word rarity when wordfreq
        # is unavailable.
        dense_terms = build_density_filter(
            emb_map,
            threshold=PROBE_MIN_DENSITY_THRESHOLD,
            k=5,
        )

    # Blocklist filter: remove terms that should never appear as probe endpoints
    before_block = len(dense_terms)
    dense_terms = {t for t in dense_terms if t.lower() not in PROBE_TERM_BLOCKLIST}
    blocked = before_block - len(dense_terms)
    if blocked:
        print(f"After blocklist filter: {len(dense_terms):,} terms ({blocked:,} blocked)")

    for c in concepts:
        if c.get("is_obsolete", False):
            continue
        term = c["label"]
        if term not in emb_map:
            continue
        if term not in dense_terms:
            continue
        vec = emb_map[term]
        cid = c["roget_category_id"]
        sid = f"{c['roget_class_id']}:{c.get('roget_section_name', '')}"
        lid = c["roget_class_id"]

        cat_map.setdefault(cid, []).append((term, vec))
        sec_map.setdefault(sid, []).append((term, vec))
        cls_map.setdefault(lid, []).append((term, vec))

        if cid not in cat_meta:
            cat_meta[cid] = {
                "category_id":   cid,
                "category_name": c["roget_category_name"],
                "section_id":    sid,
                "section_name":  c.get("roget_section_name", ""),
                "class_id":      lid,
                "class_name":    c["roget_class_name"],
            }
        if sid not in sec_meta:
            sec_meta[sid] = {
                "section_id":   sid,
                "section_name": c.get("roget_section_name", ""),
                "class_id":     lid,
                "class_name":   c["roget_class_name"],
            }

    rng    = random.Random(UMAP_RANDOM_SEED)
    levels = ["cross_class", "cross_section", "adjacent_cat"] \
             if args.level == "all" else [args.level]

    all_pairs: list[dict] = []

    for level in levels:
        print(f"\nSelecting pairs: level={level}")

        if level == "cross_class":
            class_ids = sorted(cls_map.keys())
            for i, lid_a in enumerate(class_ids):
                for lid_b in class_ids[i + 1:]:
                    meta_a = {"class_id": lid_a, "class_name": "",
                              "category_id": None, "category_name": None,
                              "section_id": None}
                    meta_b = {"class_id": lid_b, "class_name": "",
                              "category_id": None, "category_name": None,
                              "section_id": None}
                    pairs = select_pairs_from_groups(
                        cls_map[lid_a], cls_map[lid_b],
                        meta_a, meta_b, level,
                        pairs_per_group=args.pairs_per_category,
                        rng=rng, verbose=args.verbose,
                    )
                    all_pairs.extend(pairs)
                    if args.verbose:
                        print(f"  Class {lid_a} vs Class {lid_b}: {len(pairs)} pairs")

        elif level == "cross_section":
            for lid in sorted(cls_map.keys()):
                secs_in_class = [
                    sid for sid in sec_map
                    if sec_meta.get(sid, {}).get("class_id") == lid
                ]
                for i, sid_a in enumerate(secs_in_class):
                    for sid_b in secs_in_class[i + 1:]:
                        pairs = select_pairs_from_groups(
                            sec_map[sid_a], sec_map[sid_b],
                            sec_meta.get(sid_a, {}), sec_meta.get(sid_b, {}),
                            level, pairs_per_group=args.pairs_per_category,
                            rng=rng, verbose=args.verbose,
                        )
                        all_pairs.extend(pairs)

        elif level == "adjacent_cat":
            sec_to_cats: dict[str, list[str]] = {}
            for cid, cmeta in cat_meta.items():
                sec_to_cats.setdefault(cmeta["section_id"], []).append(cid)

            for sid, cids in sec_to_cats.items():
                for i, cid_a in enumerate(cids):
                    for cid_b in cids[i + 1:]:
                        pairs = select_pairs_from_groups(
                            cat_map.get(cid_a, []),
                            cat_map.get(cid_b, []),
                            cat_meta.get(cid_a, {}),
                            cat_meta.get(cid_b, {}),
                            level, pairs_per_group=args.pairs_per_category,
                            rng=rng, verbose=args.verbose,
                        )
                        all_pairs.extend(pairs)

    # Deduplicate
    seen: set[frozenset] = set()
    deduped = []
    for p in all_pairs:
        key = frozenset([p["term_a"], p["term_b"]])
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    rng.shuffle(deduped)
    final = deduped[:args.max_pairs]

    output = {
        "meta": {
            "level":                args.level,
            "pair_count":           len(final),
            "levels_included":      levels,
            "synonym_filter_cosine": SYNONYM_FILTER_COSINE,
            "percentiles":          [PROBE_PERCENTILE_LOW, 60, PROBE_PERCENTILE_HIGH],
            "timestamp":            datetime.now(timezone.utc).isoformat(),
        },
        "pairs": final,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSelected {len(final)} pairs (level={args.level})")
    print(f"Wrote: {output_path}")
    for lv in levels:
        n = sum(1 for p in final if p["level"] == lv)
        print(f"  {lv}: {n} pairs")


if __name__ == "__main__":
    main()
