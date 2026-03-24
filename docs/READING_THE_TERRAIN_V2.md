# Reading the Terrain — V2
## A Visual Guide to the Latent Language Explorer

*Sean Patrick Morris · Claude (Anthropic) · datasculptures.com · March 2026*

---

## Quick Guide

The interface has two pages. **Landscape** is the macro navigation — the full terrain with all 36,125 concept points, coloured by Roget class, animated by gradient flow. **Discovery** is where you probe for unnamed concepts: enter two terms, run a probe, read the depth, optionally request a generated description, and save to the field journal.

The terrain height is KDE (kernel density estimation) — dense clusters of named concepts form peaks, sparse transitions form valleys. **Height is not a third UMAP dimension.** The UMAP projection is two-dimensional. Height is derived separately.

The deserts are the shallow fractures between conceptual territories. A desert is not empty or meaningless. The embedding model encodes something there — it just has no name in the vocabulary. That is the point.

---

## The Terrain

The heightfield is computed from a 2D kernel density estimate over the UMAP-projected positions of all 36,125 concept terms. It is rendered as a Three.js mesh with the z-axis set to KDE density value.

**Peaks** are concentrations of named concepts — places where the vocabulary is dense and the model has strong local structure. Examples: the cluster around intellectual activity (Class 4), the cluster around emotional states (Class 6).

**Valleys** are transitions between conceptual territories — regions where the vocabulary thins and concepts begin to pull in different directions.

**Saddle points** are passes between two peaks, connecting concept regions at a lower density. The path between domains often runs through a saddle.

**Deserts** are the deep low-density regions where the KDE drops below the gate threshold. On the Landscape page, press **T** to cycle surface modes and view the desert field directly. A desert is a place where meaning exists without a name. The desert field is computed in 2D UMAP space; the probe desert is measured in 384-dimensional embedding space. These are different measurements — see the section below.

---

## The Spheres

Each concept is rendered as a sphere, coloured by its primary Roget class:

| Class | Name | Colour |
|---|---|---|
| 1 | Abstract Relations | #00b4d8 (cyan) |
| 2 | Space | #e040a0 (magenta) |
| 3 | Matter | #f07020 (orange) |
| 4 | Intellect | #4ecb71 (green) |
| 5 | Volition | #a070e0 (violet) |
| 6 | Affections | #e05050 (warm red) |

**41% of terms are polysemous** — they appear in multiple Roget categories. A polysemous term is shown in its primary category colour (the lowest-numbered category in the taxonomy). Its secondary category memberships are visible in the concept detail panel.

Sphere size scales with the term's KDE density value at its UMAP position. High-density terms (conceptual centres) appear slightly larger.

---

## Attractors and Basins

The terrain has an underlying gradient field — at each grid point, the gradient points in the direction of steepest density increase. Following the gradient from any concept term leads uphill to a local density maximum: the **attractor** for that term.

Major attractors — those that accumulate a large fraction of the vocabulary through gradient ascent — are shown pulsing faster and brighter on the Landscape page. They represent the principal peaks of the conceptual landscape.

**Basins** are the regions that drain to the same attractor. Basin boundaries are watershed lines — places where the gradient field bifurcates. A term on the boundary between two basins is conceptually ambiguous in a precise sense: small perturbations in meaning would pull it toward one peak or the other.

The basin visualization is available as a surface mode (press **T** to cycle).

---

## Two Desert Measurements

This distinction is important. Do not conflate them.

### Grid desert (2D UMAP space)

- **Computed once**, at pipeline time, on a 128×128 grid
- Measures distance from each grid cell to the nearest concept in **2D UMAP space**
- Used for: terrain surface mode (press T), dig site enumeration, visual representation
- **UMAP distorts distances.** The 2D projection compresses some regions and stretches others. Grid desert values are an approximation for visualization purposes.
- Stored in: `data/terrain/desert_field.npz`

### Probe desert (384-dimensional embedding space)

- **Computed fresh per probe**, at query time
- Measures L2 distance from the normalized probe midpoint to the nearest named concept in **full 384-dimensional embedding space**
- Used for: discovery gating, field journal recording, LLM description threshold
- **Interior steps only:** steps at alpha ∈ (0.10, 0.90) — the endpoint neighbourhoods are excluded to avoid measuring endpoint sparsity rather than the gap between domains
- **This is the genuine measurement.** It is not affected by UMAP distortion.
- Thresholds: `PROBE_DESERT_GATE_THRESHOLD = 0.50`, `PROBE_DESERT_SHALLOW_THRESHOLD = 0.70`
- Scale: L2 distance on the unit sphere, range 0–2. Typical cross-domain values: 0.70–0.93.

Do not use grid desert values to interpret probe desert values, or vice versa. They are different measurements of different things in different spaces.

---

## Pair Selection

Before a probe pair enters the discovery queue, it passes four filters:

**1. Zipf frequency ≥ 3.0** (wordfreq library, Common Crawl corpus)
Excludes rare and archaic terms from the Roget vocabulary. Without this filter, Victorian-era terms (*virgate*, *cockloft*, *nuncupation*) dominate probe endpoints. The filter uses an external corpus — not the Roget index itself — so archaic terms that cluster with other archaic terms are correctly excluded.

**2. No hyphens or underscores**
Single-word terms only. Excludes Roget compound forms like *back-stairs* and *lamb-like* that pass the frequency filter but are not clean concept words.

**3. Shared neighbourhood ≥ 1 common neighbour in top-20**
This is the key filter for discovery quality. It confirms that the two terms have at least one concept in the model's own neighbourhood that is close to both of them. A score of zero means the terms point in completely different directions with no shared vicinity — the probe would traverse generic embedding space rather than a meaningful gap. A score > 0 means the terms are approaching the same conceptual territory from different angles, which is where unnamed concepts are found.

**4. Cosine similarity ≤ 0.85**
Excludes near-synonyms. Terms this similar are too close to represent a genuine cross-domain gap.

---

## Running a Probe

1. Navigate to the **Discovery** page
2. Enter two terms in the probe input fields
3. Click **Run Probe**
4. Read the result panel:
   - **desert_max**: the maximum L2 distance from the nearest named concept, measured at interior probe steps only
   - **desert_mean**: mean over all interior steps
   - **Deepest near**: the nearest named concept at the deepest interior step — the closest named thing to the unnamed gap
   - **Probe tube**: visualized as a path through the terrain. Colour shifts blue (near concepts) → red (deep desert). A pulsing yellow ring marks the deepest interior step.
5. Click **Describe** to request a generated description (gated: requires desert > 0.50)
6. Review the description, add notes, and click **Save to Journal**

The measurement in the result panel is **384d L2 distance on the unit sphere**, not cosine distance, not 2D distance.

---

## The Field Journal

The field journal is a persistent record of all discoveries, stored as JSON + SQLite at `backend/data/journal/journal.json` and `backend/data/journal/journal.db`. It survives browser clears. Atomic writes prevent corruption on interrupt.

**Important:** Entries written via the CLI (`batch_cross_discover.py`) have `coordinates_2d = [0, 0]`. This is expected — CLI probes run in high-dimensional space without a UMAP position lookup. These entries appear as dots near the scene origin in the 3D view. They are not missing data; they simply lack a 2D position.

Filter journal entries by: desert depth, Roget class, tags, fabrication status, starred.

Export a journal entry to fabrication using the buttons in the detail panel, or via the CLI.

---

## Fabrication

Three export formats are available from a journal entry:

**Topography export** (`export_topo.py`, `POST /api/export/topo`)
A heightfield PNG showing a terrain patch centred on the probe midpoint, with optional desert overlay and journal marker contours. This is the primary fabrication reference — use it to plan CNC milling paths and manual contour work.

```bash
py scripts/export_topo.py --title "navigator vs password" --overlay-desert
```

**STL export** (`export_stl.py`, `POST /api/export/stl`)
Binary STL mesh triangulated from the terrain heightfield. For CAD reference and digital fabrication planning. Not recommended for direct 3D printing without post-processing (surface only, no base).

```bash
py scripts/export_stl.py --title "navigator vs password"
```

**Instruction sheet** (`generate_instruction_sheet.py`, `POST /api/export/sheet`)
One-page PDF fabrication guide: terrain patch diagram, contour lines at 0.25" intervals, material strategy recommendation, and step-by-step notes. The material strategy is determined by keyword matching in the concept labels — deterministic, no LLM call.

```bash
py scripts/generate_instruction_sheet.py
```

Materials used in the V1 and V2 practice: wood, cement, wire, nails, cardboard, found objects. The instruction sheet suggests a strategy; the maker decides.

---

## Keyboard Controls

| Key | Action |
|---|---|
| W / S | Move forward / backward |
| A / D | Rotate left / right |
| Q / E | Move up / down |
| Arrow keys | Strafe |
| Scroll wheel | Zoom |
| Right-drag | Free-look (mouse) |
| T | Cycle surface modes (terrain / desert / basins) |
| H | Reset to home position |
| J | Toggle field journal panel |

---

## Technical Reference

| Parameter | Value |
|---|---|
| Embedding model | all-MiniLM-L6-v2 |
| Embedding dimensions | 384 |
| PCA pre-reduction | 384d → 256d |
| UMAP components | 2 |
| UMAP random seed | 42 (never change) |
| UMAP n_neighbors | 15 |
| UMAP min_dist | 0.1 |
| KDE resolution | 128×128 grid |
| Desert field resolution | 128×128 (max 1024) |
| Probe steps | 30 |
| Interior probe range | alpha 0.10–0.90 |
| Probe gate threshold | 0.50 (L2) |
| Probe shallow threshold | 0.70 (L2) |
| Vocabulary | 36,125 terms |

For schema reference (data file formats, JSON structures, NPZ arrays): see [docs/DATA_FORMATS.md](DATA_FORMATS.md).

---

*datasculptures.com*
