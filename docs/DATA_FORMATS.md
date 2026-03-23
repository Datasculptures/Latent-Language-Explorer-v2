# Data Formats — Latent Language Explorer V2

## 1. Journal Entry Schema

Schema source: `data/schema/journal_entry.schema.json`

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string (uuid)` | yes | UUID4. Generated on creation, never reassigned. |
| `timestamp` | `string (date-time)` | yes | ISO 8601 UTC timestamp of creation. |
| `type` | `string (enum)` | yes | One of: `probe_discovery`, `dig_site`, `voronoi`, `manual`, `fabrication_note`, `v1_import`. |
| `coordinates_2d` | `[number, number]` | yes | Position in **2D UMAP layout space** `[x, y]`. NOT Three.js scene space. NOT a 3D point. |
| `coordinates_highD` | `number[] \| null` | no | Full high-dimensional embedding vector. `null` for `v1_import` entries — V1 did not store these. |
| `desert_value` | `number (≥ 0)` | yes | Distance from this point to the nearest named concept in high-D space. Higher = more isolated. |
| `nearest_concepts` | `array (max 10)` | no | Nearest named concepts at time of discovery. See sub-schema below. |
| `roget_context` | `object \| null` | no | The two Roget categories bounding this point. `null` for `v1_import` — cannot be backfilled. |
| `generated_description` | `string (max 1000) \| null` | no | LLM-generated description. HTML-entity-encoded. `null` until `/api/describe-point` is called. |
| `user_notes` | `string (max 2000)` | no | Free text. Sanitized on ingestion. Defaults to `""`. |
| `fabrication_notes` | `object` | no | Material, method, dimensions, status, photos. See sub-schema below. |
| `tags` | `string[] (max 20)` | no | User-defined tags, max 50 chars each. Sanitized. |
| `starred` | `boolean` | no | Defaults to `false`. |
| `v1_source` | `object \| null` | no | Original V1 entry preserved verbatim. Non-null only for `v1_import` entries. |
| `schema_version` | `integer` | no | Value of `SCHEMA_VERSION` at time of creation. |

**`coordinates_2d` vs `coordinates_highD` — the critical distinction:**
- `coordinates_2d` is where the entry lives on the terrain — a position in 2D UMAP layout space. This is what the frontend uses to place the marker on the map.
- `coordinates_highD` is the raw embedding vector — a position in high-D space. This is used for computing exact desert distances and cross-category probe paths.
- These are different measurements in different spaces. A `coordinates_2d` value cannot be used for high-D distance calculations, and vice versa.

**`nearest_concepts` sub-schema:**

| Field | Type | Description |
|---|---|---|
| `term` | `string (max 100)` | Concept label. Sanitized. |
| `distance` | `number (≥ 0)` | Cosine or Euclidean distance in high-D space. |
| `roget_categories` | `string[] \| null` | Roget category names for this concept. `null` for `v1_import`. |
| `roget_class` | `string \| null` | Roget class name (one of 6). `null` for `v1_import`. |

**`roget_context` sub-schema:**

| Field | Type | Description |
|---|---|---|
| `category_a` | `string` | First bounding Roget category name. |
| `category_b` | `string` | Second bounding Roget category name. |
| `section_a` | `string \| null` | Section containing `category_a`. |
| `section_b` | `string \| null` | Section containing `category_b`. |
| `class_a` | `string \| null` | One of the 6 Roget classes for `category_a`. |
| `class_b` | `string \| null` | One of the 6 Roget classes for `category_b`. |

**`fabrication_notes` sub-schema:**

| Field | Type | Description |
|---|---|---|
| `material` | `string (max 200)` | e.g., "oak", "aluminium sheet" |
| `method` | `string (max 200)` | e.g., "CNC milling", "laser etch" |
| `dimensions` | `string (max 200)` | e.g., "300mm × 300mm × 60mm" |
| `status` | `enum` | One of: `idea`, `planned`, `in_progress`, `complete` |
| `photos` | `string[] (max 20)` | File paths or URLs, max 500 chars each. |

## 2. Data Bundle Schema

Schema source: `data/schema/data_bundle.schema.json`

The data bundle is the primary pipeline output, produced by the embedding pipeline and consumed by the backend and frontend.

**`meta` object:**

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | `integer` | yes | Must match `SCHEMA_VERSION` in `terrain_config.py`. |
| `data_bundle_version` | `string` | yes | e.g., `"2.0"`. |
| `umap_random_seed` | `integer` | yes | **Must be 42.** If different, all journal `coordinates_2d` are invalid. |
| `embedding_model` | `string` | yes | e.g., `"all-MiniLM-L6-v2"`. |
| `embedding_dim` | `integer` | no | Raw embedding dimension before PCA. |
| `pca_components` | `integer` | no | PCA output dimension (target: 256). |
| `umap_components` | `integer (const: 2)` | no | **Always 2.** Terrain height is KDE density, not a UMAP dimension. |
| `term_count` | `integer` | yes | Total number of concepts in the bundle. |
| `roget_category_count` | `integer` | no | Number of distinct Roget categories represented. |
| `timestamp` | `string (date-time)` | yes | When the bundle was generated. |
| `contextual_mode` | `enum` | no | One of: `template`, `real`, `synthetic`, `none`. |
| `contextual_model` | `string \| null` | no | Model used for contextual embeddings if `contextual_mode` is `real`. |
| `pipeline_git_hash` | `string \| null` | no | Git commit hash of the pipeline that produced this bundle. |

**`concepts` array items:**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | yes | Unique concept identifier. |
| `label` | `string (max 100)` | yes | The term itself. |
| `roget_category_id` | `string` | yes | Primary Roget category ID. |
| `roget_category_name` | `string` | no | Human-readable category name. |
| `roget_section_name` | `string` | no | Section name within the class. |
| `roget_class_id` | `integer (1–6)` | yes | One of the 6 Roget classes. |
| `roget_class_name` | `string` | no | Human-readable class name. |
| `is_polysemous` | `boolean` | no | True if the term appears in more than one Roget category. |
| `all_roget_categories` | `string[]` | no | All categories this term appears in. |
| `is_modern_addition` | `boolean` | no | True if added via WordNet enrichment (not in 1911 Roget). |
| `position_2d` | `[number, number]` | yes | UMAP layout position. **Not a 3D point — see Section 2 of ARCHITECTURE.md.** |
| `context_spread` | `number \| null` | no | Standard deviation of per-context positions in 2D layout. Measures semantic ambiguity. |
| `polysemy_score` | `number \| null` | no | Composite polysemy measure. |
| `contexts` | `array` | no | Per-Roget-class contextual embedding positions. See sub-schema below. |

**`contexts` sub-schema:**

| Field | Type | Description |
|---|---|---|
| `roget_class_context` | `string` | Which Roget class template was used for this embedding. |
| `position_2d` | `[number, number]` | UMAP position for this contextual embedding. |
| `distance_from_base` | `number` | Distance from the base (neutral) embedding position in 2D. |

## 3. The v1_import Entry Type

`v1_import` entries are created by `scripts/migrate_v1_journal.py` from V1 localStorage exports.

**What is null and why:**

| Field | Value | Reason |
|---|---|---|
| `roget_context` | `null` | V1 had no Roget taxonomy integration. The concept of category-to-category positioning did not exist in V1. This cannot be computed retroactively without re-running the V1 entry's coordinates through the V2 pipeline, which is not possible because `coordinates_highD` is also null. |
| `coordinates_highD` | `null` | V1 only stored 2D positions. The high-dimensional embedding vectors were never persisted. Without them, exact desert distances and probe paths cannot be recomputed. |

**What is preserved:**

- `coordinates_2d`: the `[x, y]` position from V1. Note that V1 may have used a different UMAP seed; coordinates are carried forward as-is.
- `desert_value`: carried forward from V1.
- `user_notes`: from the V1 `note` field, sanitized.
- `nearest_concepts`: carried forward; `roget_categories` and `roget_class` set to `null`.
- `v1_source`: the complete original V1 entry JSON, preserved verbatim.

**Using v1_import entries in studio practice:**

V1 import entries appear in all journal queries and exports. Use `tags` to manually annotate them with Roget context if needed for filtering. The `user_notes` and `fabrication_notes` fields are fully editable via `PUT /api/journal/{id}`. The `starred` field works normally. The LLM description endpoint (`/api/describe-point`) can be called for these entries if `desert_value ≥ 0.02` and `nearest_concepts` is non-empty — but note the description will be based on the nearest concepts alone, not on Roget context.

## 4. API Endpoint Reference

All endpoints are prefixed with the backend host (default: `http://localhost:8000`).

| Method | Path | Status | Notes |
|---|---|---|---|
| `GET` | `/api/health` | Always available | Returns `{"status":"ok","version":"2.0.0"}`. |
| `GET` | `/api/config` | Always available | Returns non-sensitive config values for the frontend. |
| `GET` | `/api/journal` | Always available | List entries. Supports query params: `tags`, `min_desert`, `starred`, `entry_type`, `fabrication_status`, `roget_class`, `limit`, `offset`. |
| `POST` | `/api/journal` | Always available | Create entry. Body: `JournalEntryCreate`. Returns 201. |
| `GET` | `/api/journal/export` | Always available | Download full journal as JSON attachment. |
| `GET` | `/api/journal/{id}` | Always available | Get single entry by UUID. 404 if not found. |
| `PUT` | `/api/journal/{id}` | Always available | Update `user_notes`, `fabrication_notes`, `tags`, `starred`, `generated_description`. 404 if not found. |
| `POST` | `/api/describe-point` | Requires `ANTHROPIC_API_KEY` | Generate LLM description. Rate-limited: 1 call per 3 seconds. Requires `desert_value ≥ 0.02` and non-empty `nearest_concepts`. Returns 429 if rate-limited, 503 if key not configured, 422 if gate threshold not met. |
| `GET` | `/api/concepts` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/terrain` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/desert-field` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/basin-data` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/basin-assignments` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/attractors` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/voronoi-vertices` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/dig-sites` | Requires pipeline | Returns 501 until data bundle is present. |
| `GET` | `/api/taxonomy` | Requires pipeline | Returns 501 until data bundle is present. |
| `POST` | `/api/probe` | Requires pipeline | Returns 501 until data bundle is present. |
