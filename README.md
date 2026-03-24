# Latent Language Explorer V2

There are ideas that exist but do not have words. Not because they are vague or contested, but because the structure of language left them unnamed — concepts that sit in the gaps between the categories our vocabulary happens to cover. This project finds them, measures them, describes them, and materializes them as physical sculpture.

The terrain is a navigable map of the embedding space of 36,102 concepts organized by Roget's Thesaurus (1911). Peaks are dense clusters of named meaning. Valleys are transitions. The deserts — shallow fractures between conceptual territories — are where the embedding model encodes something real that has no syntactic representation in natural language.

The deserts are still shallow. The deepest measured gap is 0.9329 (L2 distance on the unit sphere in 384-dimensional space). But they are real, locatable, and consistent: run the same probe twice and you find the same gap. The computation is the instrument. The terrain is the map. The gaps are what we came to look at.

Companion to the oil painting *Are there deserts in vector space?*

---

## What's New in V2

| Dimension | V1 | V2 |
|---|---|---|
| Vocabulary source | Hand-curated, 9 domains | Roget 1911 + WordNet + modern |
| Vocabulary size | 8,735 | 36,102 |
| Taxonomy | 9 flat domains | 6 classes, ~39 sections, 991 categories |
| Embedding model | GloVe 300d (static) | all-MiniLM-L6-v2 (384d) |
| Probe measurement | Undocumented mix | 384d embedding space, interior steps only |
| Architecture | Vanilla JS, two canvases | TypeScript, React, single renderer |
| Journal storage | localStorage | JSON + SQLite, atomic writes |
| Journal entries | 14 | 548 |
| Max desert depth | 0.076 (different scale) | 0.9329 |

**Note on desert scale comparison:** V1 and V2 desert values are not directly numerically comparable. V1 used a 3D UMAP grid with an undocumented measurement mix. V2 uses 384-dimensional embedding space, interior probe steps only (alpha 0.10–0.90), with L2 distance between unit-norm vectors. Thresholds: `PROBE_DESERT_GATE_THRESHOLD = 0.50`, `PROBE_DESERT_SHALLOW_THRESHOLD = 0.70`.

---

## Quick Start

```bash
# Install dependencies (first run only)
./start.sh --install        # Mac/Linux
.\start.ps1 -Install        # Windows

# Start both servers
./start.sh
.\start.ps1
```

- Backend API docs: http://localhost:8000/api/docs
- Frontend: http://localhost:3000

---

## Running the Pipeline

The terrain data is not committed to the repo (large binary files). Run the full pipeline to generate it from scratch:

```powershell
# Windows (automated)
.\run_pipeline.ps1

# Windows (skip vocabulary rebuild, downstream only)
.\run_pipeline.ps1 -Downstream
```

```bash
# Mac/Linux (automated)
./run_pipeline.sh

# Mac/Linux (skip vocabulary rebuild)
./run_pipeline.sh --downstream
```

Manual step-by-step: see [docs/SCRIPT_REFERENCE.md](docs/SCRIPT_REFERENCE.md).

---

## Architecture

TypeScript + React + Vite frontend. Single Three.js renderer shared between the Landscape and Discovery pages. FastAPI Python backend. all-MiniLM-L6-v2 sentence-transformer embeddings. Roget's Thesaurus 1911 as taxonomic backbone. Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**The terrain height is KDE density — NOT a third UMAP dimension.** The 2D UMAP layout is (x, y). Height is derived separately from kernel density estimation. Probe desert distances are 384d L2. Grid desert is 2D UMAP L2. These are different measurements. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## UMAP Seed

```python
UMAP_RANDOM_SEED = 42   # scripts/terrain_config.py
```

**Never change this after the first embedding run.** Changing it invalidates all journal coordinates. If the seed must change, increment `SCHEMA_VERSION` and write a coordinate migration script.

---

## Pair Selection Filters

V2 applies four filters before selecting probe pairs:

1. **Zipf frequency ≥ 3.0** (wordfreq) — excludes archaic/rare terms from the Roget vocabulary using an external Common Crawl corpus. Without this filter, Victorian-era terms dominate the rankings.
2. **No hyphens or underscores** — single-word terms only, excluding compound forms like *back-stairs* and *lamb-like*.
3. **Shared neighbourhood ≥ 1 common neighbour in top-20** — confirms the two terms have common conceptual ground. Pairs with zero shared neighbourhood probe generic embedding space, not a meaningful gap.
4. **Cosine similarity ≤ 0.85** — excludes near-synonyms.

---

## Key Discoveries (V2)

**chairperson vs composure** · depth 0.9329 · deepest near: *chairman*
The region between institutional role and emotional equanimity passes through the formal exercise of authority. Something about the composure required to chair — the unnamed quality of presiding-without-reacting.

**dean vs valiant** · depth 0.9199 · deepest near: *noble*
Between an institutional title and a personal virtue lies a shared root in the idea of being worthy of regard. The unnamed concept is something like *deserved standing* — authority that derives from character rather than appointment.

**magician vs molded** · depth 0.8948 · deepest near: *quantum*
Between performance and material transformation, the embedding finds quantum physics. Something about transformation at a scale smaller than observation — change that happens without an observable mechanism. The gap between the trick and the substance.

**navigator vs password** · depth 0.8015 · deepest near: *authentication*
Between spatial wayfinding and access credentials, the model finds authentication. The unnamed concept is the moment of being recognized as authorized to proceed — the credential as a form of passage, the login as a kind of navigation.

---

## Fabrication

```bash
# Export terrain for fabrication
py scripts/export_topo.py --title "My Discovery" --overlay-desert
py scripts/export_stl.py  --title "My Discovery"
py scripts/generate_instruction_sheet.py
```

API endpoints:
- `POST /api/export/topo` — topography export with desert overlay
- `POST /api/export/stl` — binary STL mesh
- `POST /api/export/sheet` — one-page fabrication instruction PDF
- `GET  /api/exports` — list all exports
- `GET  /api/exports/{filename}` — download export file

---

## Known Limitations and Biases

These are not disclaimers. They are part of the project.

- **Victorian English vocabulary.** Roget 1911 is the backbone. The terrain reflects what was named and organized in early 20th-century English.
- **Western philosophical tradition.** Roget's six-class structure follows Leibniz and Aristotle. The gaps we find are gaps in this particular map of meaning, not gaps in meaning itself.
- **Post-1911 domains supplemented but underrepresented.** AI/ML, computing, molecular biology, and cognitive science are included but thin compared to the historical vocabulary.
- **Zipf filter (≥ 3.0) biases toward common English.** Some legitimate technical and scientific vocabulary is excluded alongside genuine archaisms. This is a known tradeoff.
- **Desert measurements are relative.** Add words to the vocabulary and the deserts shift. The measurements are properties of this vocabulary, this model, and this moment.
- **Probe desert (384d) and grid desert (2D UMAP) are different measurements** and are not interchangeable. See [docs/READING_THE_TERRAIN_V2.md](docs/READING_THE_TERRAIN_V2.md).
- **Generated descriptions are creative prompts, not ground truth.** The LLM names what it finds. Whether those names are correct is a question the project raises but does not settle.

---

## Environment Variables

```
ANTHROPIC_API_KEY    Required for generative decoding
PORT_BACKEND         Default: 8000
PORT_FRONTEND        Default: 3000
```

Copy `.env.example` to `.env`. Never commit `.env`.

---

## Project

Sean Patrick Morris · [datasculptures.com](https://datasculptures.com)
Claude (Anthropic)
Open source. See [LICENSE](LICENSE).
