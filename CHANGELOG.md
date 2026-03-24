# Changelog

## V2.0.0 — March 2026

### Architecture
- Single shared Three.js renderer replacing V1's two independent canvases
- TypeScript + React + Vite replacing vanilla JS with no build step
- Zustand state management replacing custom pub/sub AppStore
- JSON + SQLite field journal replacing localStorage

### Taxonomy
- Roget's Thesaurus 1911: 6 classes, ~39 sections, 991 categories
- WordNet enrichment: +9,349 terms (+1 hop, capped 30/category)
- Four modern domain supplements: AI/ML, Computing, Molecular Biology,
  Cognitive Science (+316 terms)
- 36,125 validated terms (vs 8,735 in V1)
- 41% polysemous terms (principled Roget multi-category membership)

### Embeddings
- all-MiniLM-L6-v2 contextual embeddings replacing GloVe 300d static
- 7 context templates per term (one per Roget class + neutral)
- PCA 384d → 256d + UMAP 2D (seed 42, documented and stable)
- Explicit 2D/384d coordinate distinction documented throughout

### Pair Selection
- Zipf frequency filter (≥ 3.0 via wordfreq): excludes archaic terms
- Hyphen/underscore filter: single tokens only
- Shared neighbourhood filter: ≥1 common neighbour in top-20
- Synonym filter: cosine similarity ≤ 0.85

### Probe Measurement
- Interior steps only: alpha ∈ (0.10, 0.90) for desert_max/mean.
  Excludes endpoint sparsity from the desert ranking.
- Normalized probe midpoints: unit sphere L2 distances
- New thresholds for L2 space:
  - `PROBE_DESERT_GATE_THRESHOLD    = 0.50`
  - `PROBE_DESERT_SHALLOW_THRESHOLD = 0.70`
- Note: not numerically comparable to V1's 0.02/0.05 thresholds
  (different measurement space and methodology)

### Discovery
- 546 probes across three hierarchy levels (cross-class, cross-section,
  adjacent-category); 548 total journal entries
- 458 DEEP (≥ 0.70), 87 shallow (0.50–0.70), 1 below gate
- Best discoveries: chairperson→composure (0.9329), dean→valiant (0.9199),
  magician→molded (0.8948), navigator→password (0.8015)
- Cross-class, cross-section, and adjacent-category levels

### Field Journal
- Persistent JSON + SQLite with atomic writes
- Full Roget context per entry (category, section, class)
- Fabrication notes field with status tracking
- V1 journal migration script (migrate_v1_journal.py)

### Fabrication
- Updated topography export with desert and journal overlays
- STL terrain patch export (binary, triangulated heightfield)
- Fabrication instruction sheet generator (one-page PDF)
- Deterministic material strategy suggestions
- Backend API: `/api/export/topo`, `/api/export/stl`, `/api/export/sheet`

---

## V1.0.0 — March 2026

Initial release. 8,735 terms, 9 hand-curated domains, GloVe 300d static
embeddings, vanilla JS frontend, localStorage journal. 14 deep discoveries
from 56 cross-domain probes. Max desert depth: 0.076 (3D UMAP grid scale,
not comparable to V2 measurements).
