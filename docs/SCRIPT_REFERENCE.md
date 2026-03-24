# Script Reference
## Latent Language Explorer V2

*Sean Patrick Morris · Claude (Anthropic) · datasculptures.com · March 2026*

All scripts are in the `scripts/` directory and are run from the project root with `py scripts/<name>.py` (Windows) or `python3 scripts/<name>.py` (Mac/Linux).

---

## Constants Reference: terrain_config.py

Single source of truth for all pipeline and configuration constants. Import from here; never hardcode values in scripts.

| Constant | Value | Purpose |
|---|---|---|
| `PROJECT_VERSION` | `"2.0.0"` | Project version string |
| `SCHEMA_VERSION` | `1` | Journal schema version; increment when schema changes |
| `UMAP_RANDOM_SEED` | `42` | UMAP random seed — **never change after first embedding run** |
| `UMAP_N_COMPONENTS` | `2` | UMAP output dimensions (2D layout) |
| `UMAP_N_NEIGHBORS` | `15` | UMAP n_neighbors parameter |
| `UMAP_MIN_DIST` | `0.1` | UMAP min_dist parameter |
| `PCA_N_COMPONENTS` | `256` | PCA pre-reduction target dimensions |
| `DESERT_FIELD_RESOLUTION` | `128` | 2D KDE desert grid resolution (cells per axis) |
| `DESERT_FIELD_MAX_RESOLUTION` | `1024` | Maximum allowed grid resolution |
| `DESERT_GATE_THRESHOLD` | `0.02` | **2D terrain only:** minimum KDE density to qualify as desert |
| `DESERT_SHALLOW_THRESHOLD` | `0.05` | **2D terrain only:** boundary between shallow and deep 2D desert |
| `DESERT_DIG_SITE_THRESHOLD` | `0.65` | Minimum desert value for a grid cell to qualify as a dig site |
| `DESERT_DIG_SITE_MIN_CELLS` | `8` | Minimum contiguous cells to form a dig site |
| `PROBE_STEPS` | `30` | Number of interpolation steps per probe |
| `PROBE_PERCENTILE_LOW` | `40` | Lower percentile for pair selection |
| `PROBE_PERCENTILE_HIGH` | `75` | Upper percentile for pair selection |
| `SYNONYM_FILTER_COSINE` | `0.85` | Maximum cosine similarity for probe pair inclusion |
| `PROBE_INTERIOR_MIN` | `0.10` | Minimum alpha for interior step scoring |
| `PROBE_INTERIOR_MAX` | `0.90` | Maximum alpha for interior step scoring |
| `PROBE_MIN_DENSITY_THRESHOLD` | `0.70` | Max mean-5-NN distance for density filter (fallback when wordfreq unavailable) |
| `PROBE_MIN_ZIPF_FREQUENCY` | `3.0` | Minimum Zipf frequency for probe endpoint inclusion |
| `PROBE_DESERT_GATE_THRESHOLD` | `0.50` | **Probe scoring:** minimum L2 to qualify as a discovery |
| `PROBE_DESERT_SHALLOW_THRESHOLD` | `0.70` | **Probe scoring:** boundary between shallow and deep discovery |
| `LLM_MODEL` | `"claude-haiku-4-5"` | Anthropic model for generative decoding |
| `LLM_MAX_TOKENS` | `150` | Maximum tokens per LLM response |
| `LLM_RATE_LIMIT_PER_HOUR` | `60` | LLM calls per hour (backend enforced) |
| `LLM_RATE_LIMIT_INTERVAL_SECONDS` | `3` | Minimum seconds between LLM calls |
| `VOCAB_MIN_TERM_LENGTH` | `4` | Minimum character length for vocabulary terms |
| `VOCAB_WORDNET_HOP_DEPTH` | `1` | WordNet enrichment hop depth |
| `VOCAB_MODERN_DOMAIN_CAP` | `4` | Maximum number of modern domain supplements |
| `VOCAB_MODERN_DOMAIN_TERM_CAP` | `100` | Maximum terms per modern domain |
| `EXPORT_DEFAULT_GRID_SIZE` | `48` | Default fabrication export grid size |
| `EXPORT_DEFAULT_BASE_INCHES` | `12.0` | Default base dimension in inches |
| `EXPORT_DEFAULT_MAX_HEIGHT_INCHES` | `6.0` | Maximum terrain height in inches |
| `EXPORT_CONTOUR_INTERVAL_INCHES` | `0.25` | Contour line interval in inches |
| `EXPORT_DPI` | `300` | Export image DPI |
| `EXPORT_MAX_GRID_DIMENSION` | `1024` | Maximum export grid dimension |
| `MAX_QUERY_LENGTH` | `500` | Maximum length for user query strings |
| `MAX_CONCEPT_LABEL_LENGTH` | `100` | Maximum length for concept labels |
| `MAX_USER_NOTE_LENGTH` | `2000` | Maximum length for journal user notes |
| `MAX_TAG_LENGTH` | `50` | Maximum length for tags |
| `MAX_TAGS_PER_ENTRY` | `20` | Maximum tags per journal entry |
| `MAX_JOURNAL_ENTRIES` | `50000` | Maximum total journal entries |
| `JOURNAL_FILENAME` | `"journal.json"` | Journal JSON filename |
| `JOURNAL_INDEX_FILENAME` | `"journal.db"` | Journal SQLite index filename |
| `DATA_BUNDLE_VERSION` | `"2.0"` | Data bundle schema version |

**Note:** `DESERT_GATE_THRESHOLD` and `DESERT_SHALLOW_THRESHOLD` are for the 2D terrain grid (KDE density values, normalized 0–1). `PROBE_DESERT_GATE_THRESHOLD` and `PROBE_DESERT_SHALLOW_THRESHOLD` are for probe measurements (384d L2 distance on the unit sphere). These scales are incompatible and must not be mixed.

---

## Vocabulary Pipeline

### parse_roget.py
**Purpose:** Parse the Roget 1911 source text into structured JSON.

**Inputs:** `data/roget/roget_1911.txt` (source text)
**Outputs:** `data/roget/roget_parsed.json`

**Notes:** Run once per project. The parsed output is the foundation of the taxonomy. Do not edit `roget_parsed.json` by hand.

---

### filter_vocab.py
**Purpose:** Apply length and quality filters to the raw Roget vocabulary.

**Inputs:** `data/roget/roget_parsed.json`
**Outputs:** `data/roget/vocab_filtered.json`

**Key filters:** Minimum term length (`VOCAB_MIN_TERM_LENGTH = 4`), removal of punctuation-only terms, deduplication within categories.

---

### enrich_wordnet.py
**Purpose:** Extend vocabulary by adding WordNet synonyms and hyponyms up to 1 hop from existing Roget terms.

**Inputs:** `data/roget/vocab_filtered.json`
**Outputs:** `data/roget/vocab_wordnet.json`

**Key arguments:**
- `--hop-depth` — WordNet hop depth (default: `VOCAB_WORDNET_HOP_DEPTH = 1`)
- `--cap` — Maximum new terms per category (default: 30)

**Notes:** Requires NLTK with WordNet corpus installed.

---

### add_modern_domains.py
**Purpose:** Supplement the vocabulary with terms from four modern domains not covered by Roget 1911: AI/ML, Computing, Molecular Biology, Cognitive Science.

**Inputs:** `data/roget/vocab_wordnet.json`, `data/roget/modern_domains/`
**Outputs:** `data/roget/roget_modern.json`

**Notes:** Capped at `VOCAB_MODERN_DOMAIN_TERM_CAP = 100` terms per domain. These additions are flagged as `is_modern_addition = True` in the taxonomy.

---

### build_vocab_index.py
**Purpose:** Build per-term category membership index and flat vocabulary list from the modern-enriched taxonomy.

**Inputs:** `data/roget/roget_modern.json`
**Outputs:**
- `data/roget/vocab_index.json` — per-term category membership
- `data/roget/vocab_flat.json` — flat list of all kept terms with metadata
- `data/roget/category_colours.json` — colour assignment per Roget class

**Notes:** Terms appearing in multiple categories are flagged `is_polysemous = True`. The `is_obsolete` flag is set if **any** category membership marks the term obsolete.

---

### validate_vocab.py
**Purpose:** Run quality checks on the assembled vocabulary before proceeding to embeddings.

**Inputs:** `data/roget/vocab_flat.json`, `data/roget/vocab_index.json`
**Outputs:** `data/roget/vocab_validated.json`

**Checks:** Minimum term length, duplicate detection, class coverage, polysemy rate.

---

## Embedding Pipeline

### compute_base_embeddings.py
**Purpose:** Compute one 384-dimensional embedding per term using the neutral context template.

**Inputs:** `data/roget/vocab_validated.json`
**Outputs:**
- `data/embeddings/base_embeddings.npz` — shape (N, 384), float32
- `data/embeddings/base_embeddings_meta.json` — model, dimensions, term count, timestamp

**Notes:** Checkpoints every 5,000 terms. If interrupted, restart picks up from the checkpoint. Embeddings are L2-normalized (unit sphere). Model: `all-MiniLM-L6-v2`.

---

### compute_contextual_embeddings.py
**Purpose:** Compute 7 context-specific embeddings per term (one per Roget class + neutral), using the `CONTEXT_TEMPLATES` from terrain_config.py.

**Inputs:** `data/roget/vocab_validated.json`
**Outputs:** `data/embeddings/contextual_embeddings.npz`

**Notes:** Checkpoints to avoid losing progress. Used for polysemy scoring and context-sensitive analysis.

---

### compute_umap.py
**Purpose:** Project base embeddings from 384d → 256d (PCA) → 2D (UMAP).

**Inputs:** `data/embeddings/base_embeddings.npz`
**Outputs:** `data/terrain/umap_coords.npz` — shape (N, 2), float32

**Notes:** Uses `UMAP_RANDOM_SEED = 42`. **Never change this seed** after the first run. Changing it invalidates all journal coordinates. PCA pre-reduction uses `PCA_N_COMPONENTS = 256`.

---

### compute_density.py
**Purpose:** Compute KDE density field over the 2D UMAP layout.

**Inputs:** `data/terrain/umap_coords.npz`
**Outputs:** `data/terrain/density_field.npz` — shape (RESOLUTION, RESOLUTION), float32

**Notes:** Resolution defaults to `DESERT_FIELD_RESOLUTION = 128`. KDE bandwidth is set automatically. The density field determines terrain height in the renderer.

---

### compute_gradients.py
**Purpose:** Compute the gradient field from the density field.

**Inputs:** `data/terrain/density_field.npz`
**Outputs:** `data/terrain/gradient_field.npz` — shape (RESOLUTION, RESOLUTION, 2), float32

**Notes:** Gradient field is used for attractor computation and basin boundary visualization.

---

### compute_attractors.py
**Purpose:** Find local density maxima (attractors) by gradient ascent.

**Inputs:** `data/terrain/density_field.npz`, `data/terrain/umap_coords.npz`
**Outputs:** `data/terrain/attractors.json`

---

### compute_basins.py
**Purpose:** Assign each concept to a basin by following gradient ascent to its attractor.

**Inputs:** `data/terrain/attractors.json`, `data/terrain/umap_coords.npz`
**Outputs:** `data/terrain/basins.json`

---

### compute_desert_field.py
**Purpose:** Compute the 2D desert field — distance from each grid cell to the nearest concept in UMAP space.

**Inputs:** `data/terrain/umap_coords.npz`
**Outputs:** `data/terrain/desert_field.npz` — shape (RESOLUTION, RESOLUTION), float32

**Notes:** Values are 2D L2 distances (not 384d probe distances). Subject to UMAP distortion. Used for visualization and dig site enumeration only.

---

### assemble_bundle.py
**Purpose:** Assemble all data into the single `data_bundle.json` served by the backend.

**Inputs:** `data/terrain/`, `data/roget/vocab_flat.json`, `data/embeddings/base_embeddings_meta.json`
**Outputs:** `backend/data/data_bundle.json`

**Notes:** The bundle is the single source of truth for the frontend and backend. It includes all concept metadata, UMAP coordinates, terrain fields, attractor positions, and basin assignments.

---

## Discovery Tools

### select_probe_pairs.py
**Purpose:** Select concept pairs for cross-category probing using hierarchy-aware selection.

**Inputs:** `backend/data/data_bundle.json`, `data/embeddings/base_embeddings.npz`
**Outputs:** `data/discovery/probe_pairs_{level}.json`

**Key arguments:**
- `--level` — `cross_class`, `cross_section`, `adjacent_cat`, or `all`
- `--pairs-per-category` — pairs to select per category pair (default: 3)
- `--max-pairs` — maximum total output pairs (default: 1000)
- `--output` — output path
- `--verbose` — print per-class-pair counts

**Filters applied:**
1. Norm filter: exclude terms with L2 norm < 0.5
2. Hyphen filter: exclude hyphenated or underscore-containing terms
3. Zipf frequency filter: exclude terms below `PROBE_MIN_ZIPF_FREQUENCY = 3.0`
4. Density filter (fallback): if wordfreq unavailable, apply mean-5-NN distance filter
5. Shared neighbourhood: require ≥1 common neighbour in top-20
6. Synonym filter: cosine similarity ≤ `SYNONYM_FILTER_COSINE = 0.85`
7. Morphological variants: exclude pairs where one is a prefix of the other

**Ordering constraint:** Must run after `assemble_bundle.py` and `compute_base_embeddings.py`.

---

### probe_lib.py
**Purpose:** Core probe computation library (no web framework dependencies). Used by both `batch_cross_discover.py` (CLI) and the FastAPI backend.

**Key classes:**
- `EmbeddingIndex` — loads base embeddings, builds KD-tree, provides `nearest_k()` and `get_embedding()` methods
- `ProbeStep` — one step in a probe: position, nearest term, desert value
- `ProbeResult` — full probe result: steps, deepest step, desert_max, desert_mean, is_deep, is_shallow

**Key functions:**
- `run_probe(index, term_a, term_b)` — run a probe between two terms; returns `ProbeResult` or `None`
- `probe_result_to_dict(result)` — serialize to JSON-safe dict

**Notes:** Desert values are L2 distances in 384d space. Only interior steps (alpha 0.10–0.90) are used for `desert_max` and `desert_mean`. Midpoints are normalized to the unit sphere before KD-tree queries.

---

### batch_cross_discover.py
**Purpose:** Run probes on a set of pre-selected pairs and optionally record discoveries in the field journal.

**Inputs:** A `probe_pairs_*.json` file (output of `select_probe_pairs.py`)
**Outputs:**
- `data/discovery/discoveries_{timestamp}.json`
- Optionally: journal entries via backend API

**Key arguments:**
- `--pairs` — path to probe pairs JSON file
- `--journal` — write discoveries to the field journal
- `--describe` — request LLM descriptions for deep deserts (requires backend running with API key)
- `--min-desert` — minimum desert_max to record (default: `PROBE_DESERT_GATE_THRESHOLD`)
- `--top N` — process only the top N pairs by highD distance
- `--dry-run` — run probes and print results but do not write journal
- `--yes` — skip cost confirmation prompt
- `--api-url` — backend URL (default: http://localhost:8000)
- `--verbose`

**Notes:** LLM calls are proxied through the backend; the API key never appears in CLI code.

---

### discovery_report.py
**Purpose:** Summarize all probe_discovery journal entries and generate a machine-readable report.

**Inputs:** `backend/data/journal/journal.json`
**Outputs:** `data/discovery/discovery_report.json`

**Notes:** Loads from the journal (canonical source) rather than individual discovery files. Prints a summary table and writes JSON with total_probed, deep_count, v2_max_desert, top5, and level breakdown.

---

### find_dig_sites.py
**Purpose:** Enumerate candidate dig sites — contiguous desert regions above the dig site threshold.

**Inputs:** `data/terrain/desert_field.npz`, `backend/data/data_bundle.json`
**Outputs:** `data/discovery/dig_sites.json`

**Notes:** A dig site requires ≥ `DESERT_DIG_SITE_MIN_CELLS = 8` contiguous grid cells above `DESERT_DIG_SITE_THRESHOLD = 0.65`.

---

### compute_voronoi.py
**Purpose:** Compute Voronoi decomposition of concept positions for spatial analysis.

**Inputs:** `data/terrain/umap_coords.npz`, `backend/data/data_bundle.json`
**Outputs:** `data/discovery/voronoi.json`

---

## Fabrication Tools

### export_topo.py
**Purpose:** Export a heightfield terrain patch as a fabrication-ready topography diagram.

**Inputs:** `data/terrain/density_field.npz`, `data/terrain/desert_field.npz`, `backend/data/journal/journal.json`
**Outputs:** `backend/data/exports/topo_{title}_{timestamp}.png`

**Key arguments:**
- `--title` — entry title or search term
- `--grid-size` — output grid size (default: `EXPORT_DEFAULT_GRID_SIZE = 48`)
- `--base-inches` — base dimension in inches (default: 12.0)
- `--max-height-inches` — maximum terrain height (default: 6.0)
- `--overlay-desert` — overlay desert field contours
- `--output-dir` — output directory

**Notes:** Contour interval: `EXPORT_CONTOUR_INTERVAL_INCHES = 0.25`. Output DPI: 300.

---

### export_stl.py
**Purpose:** Export terrain patch as binary STL mesh for CNC/3D reference.

**Inputs:** `data/terrain/density_field.npz`
**Outputs:** `backend/data/exports/terrain_{title}_{timestamp}.stl`

**Key arguments:** `--title`, `--grid-size`, `--output-dir`

**Notes:** Surface only (no base). Binary STL format. Use in CAD software for reference; not recommended for direct FDM printing without adding a base.

---

### generate_instruction_sheet.py
**Purpose:** Generate a one-page PDF fabrication instruction sheet for a journal entry.

**Inputs:** `backend/data/journal/journal.json`, `data/terrain/density_field.npz`
**Outputs:** `backend/data/exports/sheet_{title}_{timestamp}.pdf`

**Key arguments:** `--title`, `--output-dir`

**Notes:** Material strategy is determined by keyword matching in concept labels — deterministic, no LLM call. Falls back to depth-based strategy for deep deserts (≥0.07 grid desert scale).

---

## Utilities

### migrate_v1_journal.py
**Purpose:** Migrate V1 field journal entries (localStorage format) to V2 JSON schema.

**Inputs:** `data/migration/v1_journal.json` (exported from browser localStorage)
**Outputs:** Appended entries in `backend/data/journal/journal.json`

**Notes:** V1 journal coordinates are in V1 UMAP space and are not directly transferable to V2. Migrated entries have `v1_source = True` and approximate coordinates.

---

## Pipeline Automation

### run_pipeline.ps1 (Windows)
Full pipeline automation with optional `-Downstream` flag to skip vocabulary rebuild.

```powershell
.\run_pipeline.ps1             # Full pipeline
.\run_pipeline.ps1 -Downstream # Embeddings and downstream only
```

### run_pipeline.sh (Mac/Linux)
```bash
./run_pipeline.sh
./run_pipeline.sh --downstream
```

**Pipeline stages:**
1. **Vocabulary:** parse_roget → filter_vocab → enrich_wordnet → add_modern_domains → build_vocab_index → validate_vocab
2. **Embeddings:** compute_base_embeddings → compute_contextual_embeddings → compute_umap → compute_density → compute_gradients → compute_attractors → compute_basins → compute_desert_field → assemble_bundle
3. **Discovery:** find_dig_sites → compute_voronoi

**Ordering constraints:**
- Vocabulary pipeline must complete before any embedding script
- `compute_umap.py` must run before `compute_density.py`
- `compute_density.py` must run before `compute_gradients.py`
- `compute_attractors.py` must run before `compute_basins.py`
- `assemble_bundle.py` must run last in the embedding stage
- `select_probe_pairs.py` requires a complete data bundle
- `batch_cross_discover.py` requires the backend server to be running (for journal writes)

---

*datasculptures.com*
