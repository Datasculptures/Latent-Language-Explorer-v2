"""
Generates kaggle_notebook/latent_language_explorer.ipynb
Run from project root: py scripts/create_notebook.py
"""
from pathlib import Path
import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

def md(src): return new_markdown_cell(src)
def code(src): return new_code_cell(src)

# ──────────────────────────────────────────────────────────────────
# Cell 1 — Title
# ──────────────────────────────────────────────────────────────────
C1 = md("""\
# Latent Language Explorer — Roget Semantic Terrain

**Mapping the uncharted spaces between English words**

This notebook explores the semantic landscape of **36,000+ vocabulary terms** drawn from
Roget's Thesaurus, embedded with `all-MiniLM-L6-v2` and projected into a 2-D UMAP terrain.
It demonstrates how to identify *semantic deserts* — probe points that sit unexpectedly far
from any known concept in high-dimensional embedding space.

**What you'll find here:**
- A visual map of the English semantic terrain coloured by Roget's 6 top-level classes
- Morphological patterns preserved in the UMAP layout
- The distribution and character of 3,000+ discovered semantic deserts
- Live probing: encode the midpoint between two words and find its nearest neighbours
- Analysis of which class-pairs produce the deepest deserts
""")

# ──────────────────────────────────────────────────────────────────
# Cell 2 — Setup and imports
# ──────────────────────────────────────────────────────────────────
C2 = code("""\
import subprocess, sys
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "sentence-transformers", "umap-learn", "pyarrow"],
    check=True
)

import html, json, re, textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from IPython.display import display

# ── Data path ────────────────────────────────────────────────────
DATA_PATH = Path("/kaggle/input/roget-semantic-terrain")
if not DATA_PATH.exists():
    DATA_PATH = Path("kaggle_export")
print("Data path:", DATA_PATH)
assert DATA_PATH.exists(), f"Data not found at {DATA_PATH}"

# ── Roget class names ────────────────────────────────────────────
CLASS_NAMES = {
    1: "Abstract Relations",
    2: "Space",
    3: "Matter",
    4: "Intellect",
    5: "Volition",
    6: "Affections",
}

# ── Class colours (pipeline values) ─────────────────────────────
CLASS_COLORS = {
    1: "#00b4d8",
    2: "#e040a0",
    3: "#f07020",
    4: "#4ecb71",
    5: "#a070e0",
    6: "#e05050",
}

# ── Pre-initialise globals used by probe functions ───────────────
term_to_idx = {}
embeddings   = None
sample       = None
SAMPLE_SIZE  = 2000
""")

# ──────────────────────────────────────────────────────────────────
# Cell 3 — Load and describe dataset
# ──────────────────────────────────────────────────────────────────
C3 = code("""\
concepts    = pd.read_parquet(DATA_PATH / "concepts.parquet")
discoveries = pd.read_parquet(DATA_PATH / "discoveries.parquet")
probe_pairs = pd.read_parquet(DATA_PATH / "probe_pairs.parquet")

with open(DATA_PATH / "taxonomy.json",       encoding="utf-8") as f:
    taxonomy = json.load(f)
with open(DATA_PATH / "terrain_summary.json", encoding="utf-8") as f:
    terrain_summary = json.load(f)
with open(DATA_PATH / "discovery_report.json", encoding="utf-8") as f:
    discovery_report = json.load(f)

meta = terrain_summary["meta"]

print(f"Concepts:     {len(concepts):>6,}  terms  "
      f"across {concepts['roget_category_id'].nunique()} Roget categories")
print(f"Discoveries:  {len(discoveries):>6,}  probed desert points "
      f"({discoveries['depth_class'].value_counts().get('deep', 0)} deep, "
      f"{discoveries['depth_class'].value_counts().get('shallow', 0)} shallow)")
print(f"Probe pairs:  {len(probe_pairs):>6,}  candidate term pairs")
print(f"Taxonomy:     {len(taxonomy):>6}  top-level classes")
print()
print(f"Embedding model : {meta['embedding_model']}")
print(f"Embedding dims  : {meta['embedding_dim']}")
print(f"UMAP seed       : {meta['umap_random_seed']}")
print(f"Pipeline version: {meta['data_bundle_version']}")
print()
print("Concepts per Roget class:")
class_counts = (
    concepts
    .groupby(["roget_class_id", "roget_class_name"])
    .size()
    .rename("term_count")
    .reset_index()
    .sort_values("roget_class_id")
)
display(class_counts)
""")

# ──────────────────────────────────────────────────────────────────
# Cell 4 — Markdown: The Terrain
# ──────────────────────────────────────────────────────────────────
C4 = md("""\
## The Semantic Terrain

### How it was built

Every vocabulary term was embedded using **`all-MiniLM-L6-v2`** — a sentence transformer
that maps text into a 384-dimensional vector where semantically similar words cluster
together. Each term was embedded in five paraphrase templates to capture contextual
meaning, then mean-pooled into a single vector.

The high-dimensional embeddings were compressed to **256 principal components**
(retaining 97.7% of variance) then projected to **2D via UMAP** — producing a layout
where related words appear near each other and Roget's six classes form distinct
neighbourhoods.

### Roget's six classes

| ID | Class | Character |
|----|-------|-----------|
| 1 | **Abstract Relations** | Quantity, order, time, number, causation |
| 2 | **Space** | Position, form, motion, size |
| 3 | **Matter** | Senses, materials, the physical world |
| 4 | **Intellect** | Thought, knowledge, language, communication |
| 5 | **Volition** | Will, action, authority, property |
| 6 | **Affections** | Feelings, morality, society, religion |

The UMAP projects these six families into a roughly circular arrangement. The *tension*
between classes — particularly Abstract Relations (1) vs Affections (6), and Space (2)
vs Intellect (4) — drives the desert regions that appear at class boundaries.
""")

# ──────────────────────────────────────────────────────────────────
# Cell 5 — UMAP terrain visualisation (two plots)
# ──────────────────────────────────────────────────────────────────
C5 = code("""\
fig, axes = plt.subplots(1, 2, figsize=(18, 7))

# ── Plot 1: full terrain coloured by Roget class ─────────────────
ax = axes[0]
for cid in sorted(CLASS_NAMES):
    mask = concepts["roget_class_id"] == cid
    ax.scatter(
        concepts.loc[mask, "umap_x"],
        concepts.loc[mask, "umap_y"],
        c=CLASS_COLORS[cid],
        s=1.2, alpha=0.35,
        label=f"{cid}. {CLASS_NAMES[cid]}",
        rasterized=True,
    )
ax.set_title(f"36,000+ Terms — UMAP Semantic Terrain", fontsize=13, fontweight="bold")
ax.set_xlabel("UMAP-1")
ax.set_ylabel("UMAP-2")
ax.legend(loc="upper right", fontsize=8, markerscale=4, framealpha=0.85)
ax.set_aspect("equal")

# ── Plot 2: terrain with discovered desert probes overlaid ───────
ax = axes[1]
for cid in sorted(CLASS_NAMES):
    mask = concepts["roget_class_id"] == cid
    ax.scatter(
        concepts.loc[mask, "umap_x"],
        concepts.loc[mask, "umap_y"],
        c=CLASS_COLORS[cid],
        s=1.2, alpha=0.18,
        rasterized=True,
    )

# Look up 2D position of nearest_term_1 as a proxy for probe location
coord_map = concepts.set_index("term")[["umap_x", "umap_y"]].to_dict("index")

for depth, marker, color, size, label in [
    ("deep",    "*", "#ffdd00", 45, "Deep desert (≥0.70)"),
    ("shallow", "D", "#ffffff", 18, "Shallow desert (0.50–0.70)"),
]:
    sub = discoveries[discoveries["depth_class"] == depth]
    xs, ys = [], []
    for nt in sub["nearest_term_1"]:
        if nt in coord_map:
            xs.append(coord_map[nt]["umap_x"])
            ys.append(coord_map[nt]["umap_y"])
    ax.scatter(xs, ys, c=color, s=size, marker=marker, zorder=5,
               edgecolors="black", linewidths=0.4,
               label=f"{label} (n={len(sub):,})")

ax.set_title("Terrain with Discovered Desert Probes", fontsize=13, fontweight="bold")
ax.set_xlabel("UMAP-1")
ax.set_ylabel("UMAP-2")
ax.legend(loc="upper right", fontsize=9, framealpha=0.85)
ax.set_aspect("equal")

plt.tight_layout()
plt.show()
plt.close()
""")

# ──────────────────────────────────────────────────────────────────
# Cell 6 — Morphological clustering visualisation
# ──────────────────────────────────────────────────────────────────
C6 = code("""\
SUFFIX_GROUPS = [
    ("-tion / -sion",  r"(tion|sion)$",   "#e74c3c"),
    ("-ness",          r"ness$",           "#3498db"),
    ("-ment",          r"ment$",           "#2ecc71"),
    ("-ity / -ty",     r"i?ty$",           "#f39c12"),
    ("-ing",           r"ing$",            "#9b59b6"),
]

fig, axes = plt.subplots(1, len(SUFFIX_GROUPS), figsize=(20, 4))

umap_x = concepts["umap_x"].values
umap_y = concepts["umap_y"].values
terms  = concepts["term"].values

for ax, (label, pattern, color) in zip(axes, SUFFIX_GROUPS):
    mask = pd.Series(terms).str.contains(pattern, regex=True, na=False).values
    ax.scatter(umap_x[~mask], umap_y[~mask],
               c="#cccccc", s=0.4, alpha=0.15, rasterized=True)
    ax.scatter(umap_x[mask],  umap_y[mask],
               c=color,     s=1.5, alpha=0.75, rasterized=True)
    ax.set_title(f"{label}\\n({mask.sum():,} terms)", fontsize=10)
    ax.set_aspect("equal")
    ax.axis("off")

fig.suptitle(
    "Morphological Clustering: Suffix Groups in UMAP Space\\n"
    "(coloured = matching terms; grey = rest of vocabulary)",
    fontsize=12, y=1.03
)
plt.tight_layout()
plt.show()
plt.close()
""")

# ──────────────────────────────────────────────────────────────────
# Cell 7 — Markdown: What is a desert
# ──────────────────────────────────────────────────────────────────
C7 = md("""\
## Semantic Deserts

A **semantic desert** is a probe point in high-dimensional embedding space that sits
unusually *far* from every known vocabulary term — a gap in the conceptual landscape
that Roget's 36,000-term lexicon doesn't directly name.

### How probes are found

1. **Candidate pairs** are drawn from terms in different Roget classes (*cross-class*),
   different sections (*cross-section*), or adjacent categories (*adjacent*).
2. The **midpoint** of the two 384-dimensional embedding vectors is computed.
3. The **L2 distance** from that midpoint to the nearest known concept is measured —
   this is the *desert value*.
4. Points above a threshold are classified as *deep* (≥ 0.70) or *shallow* (0.50–0.70).

### What deserts mean

A deep desert probe sits where no single English word lives but where the sentence
transformer clearly *expects* meaning. These gaps might represent:

- **Conceptual blends** — ideas that mix two distant domains in ways no single word captures
- **Missing vocabulary** — concepts named in other languages but not this lexicon
- **Emergent meanings** — regions where new jargon or neologisms are forming
- **Translation surfaces** — zones between technical registers (medical ↔ lay language)

The deepest discovered desert in this dataset (**ridge vs flanking**, depth ≈ 0.96)
sits between spatial/structural language and tactical/strategic language — a blend of
physical positioning and intentional movement that English addresses only obliquely.
""")

# ──────────────────────────────────────────────────────────────────
# Cell 8 — Desert depth distribution charts
# ──────────────────────────────────────────────────────────────────
C8 = code("""\
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

dv = discoveries["desert_value"].dropna()

# ── Histogram of desert values ───────────────────────────────────
ax = axes[0]
ax.hist(dv, bins=40, color="#4878d0", edgecolor="none", alpha=0.85)
ax.axvline(0.70, color="#e74c3c", linestyle="--", linewidth=1.5, label="Deep ≥ 0.70")
ax.axvline(0.50, color="#f39c12", linestyle="--", linewidth=1.5, label="Shallow ≥ 0.50")
ax.set_xlabel("Desert Value (L2 in 384d)")
ax.set_ylabel("Count")
ax.set_title("Desert Depth Distribution", fontweight="bold")
ax.legend(fontsize=9)

# ── Count by depth class ─────────────────────────────────────────
ax = axes[1]
dc = discoveries["depth_class"].value_counts()
bar_colors_dc = {"deep": "#e74c3c", "shallow": "#f39c12"}
colors_dc = [bar_colors_dc.get(k, "#888888") for k in dc.index]
bars = ax.bar(dc.index, dc.values, color=colors_dc, edgecolor="none", alpha=0.9)
ax.set_xlabel("Depth Class")
ax.set_ylabel("Count")
ax.set_title("Discoveries by Depth Class", fontweight="bold")
for bar, v in zip(bars, dc.values):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 8,
            f"{v:,}", ha="center", fontsize=11, fontweight="bold")

# ── Count by probe level ─────────────────────────────────────────
ax = axes[2]
lv = discoveries["level"].value_counts()
bar_colors_lv = {
    "cross_class":   "#4878d0",
    "cross_section": "#55a868",
    "adjacent_cat":  "#dd8452",
}
colors_lv = [bar_colors_lv.get(k, "#888888") for k in lv.index]
bars = ax.bar(lv.index, lv.values, color=colors_lv, edgecolor="none", alpha=0.9)
ax.set_xlabel("Probe Level")
ax.set_ylabel("Count")
ax.set_title("Discoveries by Probe Level", fontweight="bold")
ax.tick_params(axis="x", rotation=15)
for bar, v in zip(bars, lv.values):
    ax.text(bar.get_x() + bar.get_width() / 2, v + 8,
            f"{v:,}", ha="center", fontsize=10, fontweight="bold")

plt.tight_layout()
plt.show()
plt.close()
""")

# ──────────────────────────────────────────────────────────────────
# Cell 9 — Top discoveries table
# ──────────────────────────────────────────────────────────────────
C9 = code("""\
top = (
    discoveries
    .sort_values("desert_value", ascending=False)
    .head(15)[
        ["term_a", "term_b", "desert_value", "depth_class", "level",
         "roget_class_a", "roget_class_b", "nearest_term_1", "starred"]
    ]
    .reset_index(drop=True)
)
top.index = top.index + 1
top.columns = ["Term A", "Term B", "Depth", "Class", "Level",
               "Roget A", "Roget B", "Nearest Term", "Starred"]
top["Depth"]   = top["Depth"].round(4)
top["Starred"] = top["Starred"].map({True: "★", False: ""})

print(f"Top {len(top)} discoveries by desert depth (of {len(discoveries):,} total):\\n")
display(top)
""")

# ──────────────────────────────────────────────────────────────────
# Cell 10 — Load sentence-transformer model and encode sample
# ──────────────────────────────────────────────────────────────────
C10 = code("""\
from sentence_transformers import SentenceTransformer

SAMPLE_SIZE = 2000

print(f"Loading all-MiniLM-L6-v2 ...")
model = SentenceTransformer("all-MiniLM-L6-v2")

print(f"Sampling {SAMPLE_SIZE:,} terms from vocabulary ...")
sample       = concepts.sample(SAMPLE_SIZE, random_state=42).reset_index(drop=True)
sample_terms = sample["term"].tolist()

print("Encoding ...")
embeddings   = model.encode(sample_terms, show_progress_bar=True,
                             batch_size=64, normalize_embeddings=False)

term_to_idx  = {t: i for i, t in enumerate(sample_terms)}
print(f"\\nReady. {len(embeddings):,} terms encoded — shape {embeddings.shape}")
""")

# ──────────────────────────────────────────────────────────────────
# Cell 11 — probe() and visualize_probe()
# ──────────────────────────────────────────────────────────────────
C11 = code("""\
def probe(term_a, term_b, top_k=5):
    '''Find nearest vocabulary terms to the midpoint of two terms in 384-d space.'''
    if not term_to_idx:
        print("term_to_idx is empty — run Cell 10 first.")
        return None
    missing = [t for t in (term_a, term_b) if t not in term_to_idx]
    if missing:
        for t in missing:
            print(f"'{t}' not found in the {len(term_to_idx):,}-term sample.")
            print("  Tip: increase SAMPLE_SIZE in Cell 10 and re-run.")
        return None

    va  = embeddings[term_to_idx[term_a]]
    vb  = embeddings[term_to_idx[term_b]]
    mid = (va + vb) / 2.0

    dists      = np.linalg.norm(embeddings - mid, axis=1)
    near_idx   = np.argsort(dists)[:top_k]

    return {
        "term_a":        term_a,
        "term_b":        term_b,
        "midpoint":      mid,
        "desert_value":  float(dists[near_idx[0]]),
        "nearest": [
            {"term": sample_terms[i], "distance": float(dists[i])}
            for i in near_idx
        ],
    }


def _class_color_for(term):
    row = sample[sample["term"] == term]
    if row.empty:
        return "#888888"
    cid = row["roget_class_id"].iloc[0]
    try:
        return CLASS_COLORS[int(cid)]
    except (KeyError, ValueError):
        return "#888888"


def visualize_probe(result, note=""):
    '''Plot probe nearest-neighbours on the UMAP terrain plus a distance bar chart.'''
    if result is None:
        return

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # ── Left: UMAP scatter ───────────────────────────────────────
    ax = axes[0]
    for cid in sorted(CLASS_NAMES):
        mask = sample["roget_class_id"] == cid
        ax.scatter(
            sample.loc[mask, "umap_x"], sample.loc[mask, "umap_y"],
            c=CLASS_COLORS[cid], s=6, alpha=0.30,
            label=CLASS_NAMES[cid], rasterized=True,
        )

    # Input terms
    for term, marker in [(result["term_a"], "^"), (result["term_b"], "v")]:
        row = sample[sample["term"] == term]
        if not row.empty:
            ax.scatter(row["umap_x"], row["umap_y"],
                       c="white", s=100, marker=marker, zorder=7,
                       edgecolors="black", linewidths=1.2,
                       label=f'Input: "{term}"')

    # Approximate 2-D probe midpoint
    ra = sample[sample["term"] == result["term_a"]]
    rb = sample[sample["term"] == result["term_b"]]
    if not ra.empty and not rb.empty:
        mx = (ra["umap_x"].iloc[0] + rb["umap_x"].iloc[0]) / 2
        my = (ra["umap_y"].iloc[0] + rb["umap_y"].iloc[0]) / 2
        ax.scatter(mx, my, c="#ff3333", s=160, marker="X", zorder=8,
                   edgecolors="white", linewidths=1.5, label="Probe midpoint (approx.)")

    # Nearest concepts
    for r in result["nearest"]:
        row = sample[sample["term"] == r["term"]]
        if not row.empty:
            ax.scatter(row["umap_x"], row["umap_y"],
                       c="#ffdd00", s=70, marker="*", zorder=6,
                       edgecolors="#aa8800", linewidths=0.8)
            ax.annotate(
                r["term"],
                (row["umap_x"].iloc[0], row["umap_y"].iloc[0]),
                textcoords="offset points", xytext=(5, 5),
                fontsize=8,
                bbox=dict(boxstyle="round,pad=0.2", fc="black", alpha=0.65, ec="none"),
                color="white",
            )

    ax.set_title(
        f'Probe: "{result["term_a"]}" vs "{result["term_b"]}"\\n'
        f'Desert depth: {result["desert_value"]:.4f}',
        fontsize=11, fontweight="bold"
    )
    ax.set_xlabel("UMAP-1")
    ax.set_ylabel("UMAP-2")
    ax.legend(loc="upper right", fontsize=7, markerscale=1.5, framealpha=0.85)

    # ── Right: distance bar chart ────────────────────────────────
    ax = axes[1]
    n_terms = [r["term"]     for r in result["nearest"]]
    n_dists = [r["distance"] for r in result["nearest"]]
    bar_col = [_class_color_for(t) for t in n_terms]

    bars = ax.barh(range(len(n_terms)), n_dists, color=bar_col, edgecolor="none", alpha=0.85)
    ax.set_yticks(range(len(n_terms)))
    ax.set_yticklabels(n_terms, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("L2 distance from probe midpoint")
    ax.set_title(f"Nearest Concepts\\n(from {len(term_to_idx):,}-term sample)",
                 fontsize=11, fontweight="bold")
    ax.axvline(0.70, color="#e74c3c", linestyle="--", linewidth=1.2, label="Deep threshold 0.70")
    ax.legend(fontsize=9)
    for bar, d in zip(bars, n_dists):
        ax.text(bar.get_width() + 0.004, bar.get_y() + bar.get_height() / 2,
                f"{d:.3f}", va="center", fontsize=9)

    if note:
        fig.text(0.5, -0.02, note, ha="center", fontsize=9, style="italic", wrap=True)

    plt.tight_layout()
    plt.show()
    plt.close()
""")

# ──────────────────────────────────────────────────────────────────
# Cell 12 — Example probes (classic V1 pairs)
# ──────────────────────────────────────────────────────────────────
C12 = code("""\
# Classic pairs from early discovery sessions
CLASSIC_PAIRS = [
    ("surge",     "overwhelmed"),   # Abstract Relations × Volition
    ("apache",    "demanding"),     # Matter × Affections
    ("mercy",     "precision"),     # Affections × Abstract Relations
]

for term_a, term_b in CLASSIC_PAIRS:
    result = probe(term_a, term_b)
    if result:
        print(f'\\n"{term_a}" vs "{term_b}"')
        print(f'  Desert depth : {result["desert_value"]:.4f}')
        print(f'  Nearest terms: {", ".join(r["term"] for r in result["nearest"])}')
        visualize_probe(result)
    print("-" * 60)
""")

# ──────────────────────────────────────────────────────────────────
# Cell 13 — Interactive probe: navigator vs password
# ──────────────────────────────────────────────────────────────────
C13 = code("""\
# A hand-picked probe bridging wayfinding and access control
result = probe("navigator", "password")

if result:
    print(f'Probe: "navigator" vs "password"')
    print(f'Desert depth: {result["desert_value"]:.4f}')
    print()
    print("Nearest concepts:")
    for i, r in enumerate(result["nearest"], 1):
        row = sample[sample["term"] == r["term"]]
        cls = CLASS_NAMES.get(int(row["roget_class_id"].iloc[0]), "?") if not row.empty else "?"
        print(f"  {i}. {r['term']:<22} dist={r['distance']:.4f}  [{cls}]")

    visualize_probe(
        result,
        note=(
            'This midpoint sits between purposeful movement (navigation/wayfinding) '
            'and controlled access — a region of directed passage under constraint.'
        )
    )
""")

# ──────────────────────────────────────────────────────────────────
# Cell 14 — Browse discoveries
# ──────────────────────────────────────────────────────────────────
C14 = code("""\
# ── Starred discoveries with generated descriptions ───────────────
starred = (
    discoveries[discoveries["starred"] == True]
    .sort_values("desert_value", ascending=False)
)

print(f"Starred discoveries ({len(starred)} total):\\n")
print("=" * 72)

for _, row in starred.iterrows():
    print(f'\\n  ★  "{row["term_a"]}" vs "{row["term_b"]}"')
    print(f'     depth={row["desert_value"]:.4f} ({row["depth_class"]}) | {row["level"]}')
    print(f'     {row["roget_class_a"]}  ×  {row["roget_class_b"]}')
    print(f'     Nearest: {row["nearest_term_1"]} ({row["nearest_dist_1"]:.4f})')
    desc = row.get("generated_description") or ""
    if desc:
        for line in textwrap.wrap(desc, width=68):
            print(f'     {line}')

print()
print("=" * 72)

# ── All discoveries summary table ────────────────────────────────
print(f"\\nAll {len(discoveries):,} discoveries (sorted by depth):")
display(
    discoveries[
        ["term_a", "term_b", "desert_value", "depth_class",
         "level", "roget_class_a", "roget_class_b", "starred"]
    ]
    .sort_values("desert_value", ascending=False)
    .head(50)
    .reset_index(drop=True)
)
""")

# ──────────────────────────────────────────────────────────────────
# Cell 15 — Class pair analysis chart
# ──────────────────────────────────────────────────────────────────
C15 = code("""\
cross = discoveries[discoveries["level"] == "cross_class"].copy()

if cross.empty:
    print("No cross-class discoveries found in dataset.")
else:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    class_list = [CLASS_NAMES[k] for k in sorted(CLASS_NAMES)]
    n = len(class_list)

    # ── Heatmap: mean desert depth by class pair ─────────────────
    ax = axes[0]
    matrix = np.full((n, n), np.nan)
    pivot  = (
        cross.groupby(["roget_class_a", "roget_class_b"])["desert_value"]
        .mean()
        .reset_index()
    )
    for _, row in pivot.iterrows():
        ca, cb = row["roget_class_a"], row["roget_class_b"]
        if ca in class_list and cb in class_list:
            i = class_list.index(ca)
            j = class_list.index(cb)
            matrix[i, j] = row["desert_value"]
            matrix[j, i] = row["desert_value"]

    masked = np.ma.masked_invalid(matrix)
    im = ax.imshow(masked, cmap="YlOrRd", vmin=0.5, vmax=1.0, aspect="auto")
    short = [f"{k}. {v[:13]}" for k, v in sorted(CLASS_NAMES.items())]
    ax.set_xticks(range(n)); ax.set_xticklabels(short, rotation=35, ha="right", fontsize=9)
    ax.set_yticks(range(n)); ax.set_yticklabels(short, fontsize=9)
    ax.set_title("Mean Desert Depth by Class Pair\\n(cross-class discoveries)",
                 fontweight="bold", fontsize=11)
    plt.colorbar(im, ax=ax, label="Mean desert value")
    for i in range(n):
        for j in range(n):
            v = matrix[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.3f}", ha="center", va="center",
                        fontsize=8, color="black" if v < 0.8 else "white")

    # ── Bar chart: mean + max depth by class ─────────────────────
    ax = axes[1]

    def _cls_color(name):
        for k, v in CLASS_NAMES.items():
            if v == name:
                return CLASS_COLORS[k]
        return "#888888"

    class_avg = (
        cross.groupby("roget_class_a")["desert_value"]
        .agg(mean="mean", max="max", count="count")
        .reset_index()
        .sort_values("mean", ascending=False)
    )
    x      = np.arange(len(class_avg))
    colors = [_cls_color(n) for n in class_avg["roget_class_a"]]
    ax.bar(x, class_avg["max"],  color=colors, alpha=0.30, edgecolor="none", label="Max")
    ax.bar(x, class_avg["mean"], color=colors, alpha=0.90, edgecolor="none", label="Mean")
    ax.set_xticks(x)
    ax.set_xticklabels(class_avg["roget_class_a"].str[:15],
                       rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("Desert Value")
    ax.set_title("Desert Depth by Roget Class (as term_a)\\ncross-class discoveries",
                 fontweight="bold", fontsize=11)
    ax.legend(fontsize=9)
    for xi, (_, row) in zip(x, class_avg.iterrows()):
        ax.text(xi, row["mean"] + 0.005, f"n={int(row['count'])}",
                ha="center", fontsize=8, color="#444444")

    plt.tight_layout()
    plt.show()
    plt.close()
""")

# ──────────────────────────────────────────────────────────────────
# Cell 16 — Closing markdown
# ──────────────────────────────────────────────────────────────────
C16 = md("""\
## Summary and Next Steps

### What we found

| Observation | Detail |
|-------------|--------|
| **Terrain structure** | 36,000+ terms form 6 coherent class neighbourhoods in 2-D UMAP space |
| **Morphological clustering** | Suffix groups (-tion, -ness, -ment…) cluster visibly, confirming the embedding captures form as well as meaning |
| **Desert density** | 3,300+ desert probes collected; the majority classified as *deep* (≥ 0.70 L2) |
| **Cross-class deserts** | Class-boundary pairs (especially Abstract Relations × Affections) produce the deepest gaps |
| **Deepest discovery** | *ridge vs flanking* — depth ≈ 0.96, bridging structural and tactical language |

### Methodology recap

| Step | Detail |
|------|--------|
| Vocabulary | Roget's Thesaurus (1911) + modern additions — ~36,000 terms |
| Embeddings | `all-MiniLM-L6-v2`, 384-d, contextual template encoding |
| Reduction | PCA → 256-d (97.7% variance retained), then UMAP → 2-D (seed=21) |
| Terrain | Gaussian KDE 128×128 grid; gradient flow; attractor basin detection |
| Desert threshold | ≥ 0.70 L2 in 384-d space = deep; 0.50–0.70 = shallow |

### Further exploration

- **Increase `SAMPLE_SIZE`** (e.g. 10,000) in Cell 10 for denser probe coverage
- **Probe your own pairs** — any two terms from different semantic domains
- **Extend the vocabulary** — add domain-specific terms to find discipline-crossing deserts
- **Cross-lingual probing** — embed foreign-language terms to find concepts missing in English

---

*Dataset compiled by the Latent Language Explorer v2 project.*
*Embedding model: `sentence-transformers/all-MiniLM-L6-v2` | Taxonomy: Roget's Thesaurus (1911, public domain)*
""")

# ──────────────────────────────────────────────────────────────────
# Assemble and write notebook
# ──────────────────────────────────────────────────────────────────
nb = new_notebook()
nb.cells = [C1, C2, C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C13, C14, C15, C16]
nb.metadata = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {
        "name": "python",
        "version": "3.11.0",
    },
}

out_dir  = Path("kaggle_notebook")
out_dir.mkdir(exist_ok=True)
out_path = out_dir / "latent_language_explorer.ipynb"

with open(out_path, "w", encoding="utf-8") as f:
    nbformat.write(nb, f)

print(f"Wrote {out_path}  ({out_path.stat().st_size / 1024:.1f} KB)")
print(f"Cells: {len(nb.cells)}")
