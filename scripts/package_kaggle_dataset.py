"""
Assembles publishable artifacts into kaggle_export/ in Kaggle-ready formats.
Does not modify any source files.

Run from project root:
    py scripts/package_kaggle_dataset.py
"""

import html
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from terrain_config import PROBE_TERM_BLOCKLIST
OUT = ROOT / "kaggle_export"
OUT.mkdir(exist_ok=True)

CLASS_NAMES = {
    1: "Abstract Relations",
    2: "Space",
    3: "Matter",
    4: "Intellect",
    5: "Volition",
    6: "Affections",
}


def _mb(path: Path) -> str:
    size = path.stat().st_size
    if size >= 1_000_000:
        return f"{size / 1_000_000:.2f} MB"
    return f"{size / 1_000:.1f} KB"


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path, compression="snappy")
    print(f"  wrote {path.name}  ({_mb(path)},  {len(df):,} rows)")


def _drop_blocklisted(df: pd.DataFrame, name: str) -> pd.DataFrame:
    before = len(df)
    mask = ~df["term_a"].str.lower().isin(PROBE_TERM_BLOCKLIST) & \
           ~df["term_b"].str.lower().isin(PROBE_TERM_BLOCKLIST)
    df = df[mask]
    if len(df) < before:
        print(f"  Blocklist removed {before - len(df)} rows from {name}")
    return df


# ──────────────────────────────────────────────────────────────────
# 1. concepts.parquet
# ──────────────────────────────────────────────────────────────────

def build_concepts() -> None:
    print("\n[1/7] concepts.parquet")
    with open(ROOT / "backend/data/data_bundle.json", encoding="utf-8") as f:
        bundle = json.load(f)

    rows = []
    for c in bundle["concepts"]:
        pos = c.get("position_2d") or [None, None]
        rows.append(
            {
                "term": c.get("label", ""),
                "roget_class_id": c.get("roget_class_id"),
                "roget_class_name": c.get("roget_class_name", ""),
                "roget_category_id": c.get("roget_category_id", ""),
                "roget_category_name": c.get("roget_category_name", ""),
                "roget_section_name": c.get("roget_section_name", ""),
                "is_polysemous": bool(c.get("is_polysemous", False)),
                "is_modern_addition": bool(c.get("is_modern_addition", False)),
                "is_obsolete": bool(c.get("is_obsolete", False)),
                "umap_x": pos[0],
                "umap_y": pos[1],
                "polysemy_score": c.get("polysemy_score"),
                "context_spread": c.get("context_spread"),
                "colour": c.get("colour", ""),
            }
        )

    df = pd.DataFrame(rows)
    df["roget_class_id"] = df["roget_class_id"].astype("Int8")
    df["umap_x"] = df["umap_x"].astype("float32")
    df["umap_y"] = df["umap_y"].astype("float32")
    df["polysemy_score"] = df["polysemy_score"].astype("float32")
    df["context_spread"] = df["context_spread"].astype("float32")

    _write_parquet(df, OUT / "concepts.parquet")


# ──────────────────────────────────────────────────────────────────
# 2. discoveries.parquet
# ──────────────────────────────────────────────────────────────────

def _clean_desc(raw: str | None) -> str:
    desc = html.unescape(raw or "")
    desc = re.sub(r"\*\*([^*]+)\*\*", r"\1", desc)
    desc = re.sub(r"\\([*_])", r"\1", desc)
    return desc.strip()


def _extract_terms(user_notes: str | None):
    m = re.match(r"^(.+?)\s+vs\s+(.+)$", user_notes or "")
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


def _class_names_from_tags(tags: list[str]) -> tuple[str, str]:
    nums = []
    for t in tags:
        m = re.match(r"^class_(\d)$", t)
        if m:
            nums.append(int(m.group(1)))
    a = CLASS_NAMES.get(nums[0], "") if len(nums) > 0 else ""
    b = CLASS_NAMES.get(nums[1], "") if len(nums) > 1 else ""
    return a, b


def _level_from_tags(tags: list[str]) -> str:
    for t in tags:
        if t in ("cross_class", "cross_section", "adjacent_cat"):
            return t
    return ""


def build_discoveries() -> None:
    print("\n[2/7] discoveries.parquet")
    with open(ROOT / "backend/data/journal/journal.json", encoding="utf-8") as f:
        raw = json.load(f)
    entries = raw if isinstance(raw, list) else raw.get("entries", [])
    probes = [e for e in entries if e.get("type") == "probe_discovery"]

    rows = []
    for p in probes:
        term_a, term_b = _extract_terms(p.get("user_notes"))
        class_a, class_b = _class_names_from_tags(p.get("tags", []))
        level = _level_from_tags(p.get("tags", []))
        dv = p.get("desert_value") or 0.0
        depth_class = "deep" if dv >= 0.70 else "shallow" if dv >= 0.50 else ""

        nc = p.get("nearest_concepts") or []
        fn = p.get("fabrication_notes") or {}

        rows.append(
            {
                "id": p.get("id", ""),
                "timestamp": p.get("timestamp", ""),
                "term_a": term_a,
                "term_b": term_b,
                "desert_value": dv,
                "depth_class": depth_class,
                "roget_class_a": class_a,
                "roget_class_b": class_b,
                "level": level,
                "nearest_term_1": nc[0]["term"] if len(nc) > 0 else "",
                "nearest_dist_1": nc[0]["distance"] if len(nc) > 0 else None,
                "nearest_term_2": nc[1]["term"] if len(nc) > 1 else "",
                "nearest_dist_2": nc[1]["distance"] if len(nc) > 1 else None,
                "nearest_term_3": nc[2]["term"] if len(nc) > 2 else "",
                "nearest_dist_3": nc[2]["distance"] if len(nc) > 2 else None,
                "generated_description": _clean_desc(p.get("generated_description")),
                "starred": bool(p.get("starred", False)),
                "fabrication_status": fn.get("status", ""),
            }
        )

    df = pd.DataFrame(rows)
    for col in ("desert_value", "nearest_dist_1", "nearest_dist_2", "nearest_dist_3"):
        df[col] = df[col].astype("float32")

    df = _drop_blocklisted(df, "discoveries")
    _write_parquet(df, OUT / "discoveries.parquet")


# ──────────────────────────────────────────────────────────────────
# 3. probe_pairs.parquet
# ──────────────────────────────────────────────────────────────────

def _load_pairs_file(path: Path, level: str) -> list[dict]:
    if not path.exists():
        print(f"    (skipping missing file: {path.name})")
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    pairs = raw.get("pairs", raw) if isinstance(raw, dict) else raw
    for p in pairs:
        p["level"] = p.get("level") or level
    return pairs


def build_probe_pairs() -> None:
    print("\n[3/7] probe_pairs.parquet")
    disc = ROOT / "data/discovery"
    all_pairs = (
        _load_pairs_file(disc / "probe_pairs_cross_class.json", "cross_class")
        + _load_pairs_file(disc / "probe_pairs_cross_section.json", "cross_section")
        + _load_pairs_file(disc / "probe_pairs_adjacent.json", "adjacent_cat")
    )

    rows = []
    for p in all_pairs:
        rows.append(
            {
                "term_a": p.get("term_a", ""),
                "term_b": p.get("term_b", ""),
                "level": p.get("level", ""),
                "class_id_a": p.get("class_id_a"),
                "class_id_b": p.get("class_id_b"),
                "class_name_a": p.get("class_name_a") or CLASS_NAMES.get(p.get("class_id_a"), ""),
                "class_name_b": p.get("class_name_b") or CLASS_NAMES.get(p.get("class_id_b"), ""),
                "percentile": p.get("percentile"),
                "distance_highD": p.get("distance_highD"),
                "cosine_sim": p.get("cosine_sim"),
            }
        )

    df = pd.DataFrame(rows)
    df["class_id_a"] = df["class_id_a"].astype("Int8")
    df["class_id_b"] = df["class_id_b"].astype("Int8")
    df["percentile"] = df["percentile"].astype("Int8")
    df["distance_highD"] = df["distance_highD"].astype("float32")
    df["cosine_sim"] = df["cosine_sim"].astype("float32")

    df = _drop_blocklisted(df, "probe_pairs")
    _write_parquet(df, OUT / "probe_pairs.parquet")


# ──────────────────────────────────────────────────────────────────
# 4. taxonomy.json
# ──────────────────────────────────────────────────────────────────

def _strip_taxonomy(node: dict) -> dict:
    """Recursively strip raw_line_start/raw_line_end; flatten words to strings."""
    out = {}
    for k, v in node.items():
        if k in ("raw_line_start", "raw_line_end"):
            continue
        if k == "words" and isinstance(v, list):
            cleaned = []
            for w in v:
                if isinstance(w, str):
                    cleaned.append(w)
                elif isinstance(w, dict):
                    cleaned.append(w.get("term", w.get("word", str(w))))
            out[k] = cleaned
        elif k in ("sections", "categories") and isinstance(v, list):
            out[k] = [_strip_taxonomy(item) for item in v]
        elif isinstance(v, dict):
            out[k] = _strip_taxonomy(v)
        else:
            out[k] = v
    return out


def build_taxonomy() -> None:
    print("\n[4/7] taxonomy.json")
    with open(ROOT / "data/roget/roget_parsed.json", encoding="utf-8") as f:
        raw = json.load(f)

    classes = raw.get("classes", raw) if isinstance(raw, dict) else raw
    cleaned = [_strip_taxonomy(c) for c in classes]

    out_path = OUT / "taxonomy.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  wrote {out_path.name}  ({_mb(out_path)})")


# ──────────────────────────────────────────────────────────────────
# 5. terrain_summary.json
# ──────────────────────────────────────────────────────────────────

def build_terrain_summary() -> None:
    print("\n[5/7] terrain_summary.json")
    with open(ROOT / "backend/data/data_bundle.json", encoding="utf-8") as f:
        bundle = json.load(f)
    with open(ROOT / "backend/data/terrain_data.json", encoding="utf-8") as f:
        terrain = json.load(f)
    with open(ROOT / "data/terrain/desert_meta.json", encoding="utf-8") as f:
        desert_meta = json.load(f)

    attractors = terrain.get("attractors", [])
    basin_boundaries = terrain.get("basin_boundaries", [])

    summary = {
        "meta": bundle.get("meta", {}),
        "attractors": attractors,
        "desert_field": {
            "min": desert_meta.get("desert_min_raw"),
            "max": desert_meta.get("desert_max_raw"),
            "mean": None,
            "dig_site_count": desert_meta.get("cells_above_threshold"),
        },
        "basin_count": len(basin_boundaries),
    }

    out_path = OUT / "terrain_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  wrote {out_path.name}  ({_mb(out_path)})")


# ──────────────────────────────────────────────────────────────────
# 6. discovery_report.json
# ──────────────────────────────────────────────────────────────────

def build_discovery_report() -> None:
    print("\n[6/7] discovery_report.json")
    src = ROOT / "data/discovery/discovery_report.json"
    dst = OUT / "discovery_report.json"
    shutil.copy2(src, dst)
    print(f"  wrote {dst.name}  ({_mb(dst)})")


# ──────────────────────────────────────────────────────────────────
# 7. README.md
# ──────────────────────────────────────────────────────────────────

README = """\
# Latent Language Explorer — Semantic Desert Dataset

## Overview

This dataset accompanies the **Latent Language Explorer v2** project, which maps
the semantic landscape of the English language using the Roget's Thesaurus
taxonomy and sentence-transformer embeddings.

The project embeds 36,000+ vocabulary terms with `all-MiniLM-L6-v2` (384d),
reduces them to a 2D UMAP layout, and computes a **semantic terrain** — density
peaks, gradient flows, attractor basins, and *desert regions* (areas of low
semantic density that sit unexpectedly far from known concepts in high-dimensional
space).

---

## Files

| File | Format | Description |
|------|--------|-------------|
| `concepts.parquet` | Parquet | 36,000+ vocabulary terms with Roget classification, UMAP coordinates, polysemy and context-spread scores |
| `discoveries.parquet` | Parquet | ~45 manually probed semantic desert points with nearest-concept neighbours and generated descriptions |
| `probe_pairs.parquet` | Parquet | Cross-class term pairs used as desert probe candidates, with high-D distance and cosine similarity |
| `taxonomy.json` | JSON | Clean Roget hierarchy (6 classes → sections → categories → words) |
| `terrain_summary.json` | JSON | Terrain metadata: embedding config, attractor list, desert field stats, basin count |
| `discovery_report.json` | JSON | Aggregate statistics for all probed desert points |

---

## Schema

### concepts.parquet

| Column | Type | Description |
|--------|------|-------------|
| `term` | string | Vocabulary term |
| `roget_class_id` | int8 | Roget class (1–6) |
| `roget_class_name` | string | e.g. "Abstract Relations" |
| `roget_category_id` | string | e.g. "1.1.1" |
| `roget_category_name` | string | e.g. "Existence" |
| `roget_section_name` | string | e.g. "Abstract Existence" |
| `is_polysemous` | bool | Term appears in multiple categories |
| `is_modern_addition` | bool | Added beyond original Roget corpus |
| `is_obsolete` | bool | Marked obsolete in source |
| `umap_x` | float32 | 2D UMAP layout x coordinate |
| `umap_y` | float32 | 2D UMAP layout y coordinate |
| `polysemy_score` | float32 | 0–1 polysemy score (null if not computed) |
| `context_spread` | float32 | Mean pairwise contextual embedding distance |
| `colour` | string | Hex colour for this Roget class |

### discoveries.parquet

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | UUID |
| `timestamp` | string | ISO 8601 |
| `term_a` | string | First term from probe pair |
| `term_b` | string | Second term from probe pair |
| `desert_value` | float32 | Probe desert depth (384d L2 distance) |
| `depth_class` | string | "deep" (≥0.70) or "shallow" (0.50–0.70) |
| `roget_class_a` | string | Roget class of term_a |
| `roget_class_b` | string | Roget class of term_b |
| `level` | string | cross_class / cross_section / adjacent_cat |
| `nearest_term_1..3` | string | Nearest known concepts at probe site |
| `nearest_dist_1..3` | float32 | High-D L2 distance to nearest concepts |
| `generated_description` | string | LLM-generated semantic description |
| `starred` | bool | Manually marked as notable |
| `fabrication_status` | string | Physical fabrication planning status |

### probe_pairs.parquet

| Column | Type | Description |
|--------|------|-------------|
| `term_a`, `term_b` | string | Term pair |
| `level` | string | cross_class / cross_section / adjacent_cat |
| `class_id_a`, `class_id_b` | int8 | Roget class IDs |
| `class_name_a`, `class_name_b` | string | Roget class names |
| `percentile` | int8 | Distance percentile tier (40, 60, or 75) |
| `distance_highD` | float32 | L2 distance in 384d embedding space |
| `cosine_sim` | float32 | Cosine similarity |

---

## Methodology

1. **Vocabulary**: ~36,000 terms from Roget's Thesaurus (1911 edition + modern additions)
2. **Embeddings**: `all-MiniLM-L6-v2` via sentence-transformers (384 dimensions)
3. **Contextual embeddings**: Each term embedded in 5 template sentences; mean pooled
4. **Dimensionality reduction**: PCA to 256d (97.7% variance), then UMAP to 2D (seed=21)
5. **Terrain**: Gaussian KDE density grid (128×128), gradient flow, attractor basins
6. **Desert detection**: Grid points with low density and high distance to nearest concept
7. **Probe pairs**: Term pairs from different Roget classes/sections sampled at distance percentiles
8. **Desert probing**: Midpoint of high-D term pair vectors, measured by L2 distance to nearest concept

---

## Roget Classes

| ID | Name |
|----|------|
| 1 | Abstract Relations |
| 2 | Space |
| 3 | Matter |
| 4 | Intellect |
| 5 | Volition |
| 6 | Affections |

---

## Citation

If you use this dataset, please cite the Latent Language Explorer v2 project.

Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
Taxonomy source: Roget's Thesaurus (1911, public domain)
"""


def build_readme() -> None:
    print("\n[7/7] README.md")
    out_path = OUT / "README.md"
    out_path.write_text(README, encoding="utf-8")
    print(f"  wrote {out_path.name}  ({_mb(out_path)})")


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Output directory: {OUT}")
    build_concepts()
    build_discoveries()
    build_probe_pairs()
    build_taxonomy()
    build_terrain_summary()
    build_discovery_report()
    build_readme()

    total = sum(f.stat().st_size for f in OUT.iterdir() if f.is_file())
    print(f"\nDone. Total kaggle_export/ size: {total / 1_000_000:.2f} MB")


if __name__ == "__main__":
    main()
