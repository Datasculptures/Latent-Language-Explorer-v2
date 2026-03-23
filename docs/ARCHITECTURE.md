# Architecture — Latent Language Explorer V2

## 1. Data Flow

The pipeline runs in this order, entirely offline (no HTTP):

```
Roget's 1911 taxonomy (parsed)
  → WordNet enrichment
  → Filtered vocabulary (~20,000–50,000 terms)
  → Contextual embeddings (sentence-transformers, 6 template sentences per term)
  → PCA reduction (→ 256d)
  → UMAP layout (→ 2D, seed 42)
  → KDE density field (→ heightfield for terrain)
  → Desert field (128×128 grid in 2D UMAP space)
  → Cross-category probing (high-D space)
  → Generative decoding (gated on desert_value ≥ 0.02)
  → Field journal (JSON on disk, SQLite index)
  → Fabrication export (PDF/PNG/CSV/STL)
```

Each stage writes to `backend/data/` and is independently re-runnable. The pipeline scripts live in `scripts/`. Constants controlling every stage are defined in `scripts/terrain_config.py` — no magic numbers elsewhere.

## 2. The 2D/3D Distinction — CRITICAL

This is the single most common source of confusion in this project. State it plainly:

- **The embedding layout is 2D UMAP.** `position_2d` in all schemas is `[x, y]`.
- **The terrain height (`z` in the Three.js scene) is KDE density extruded as a heightfield.** It is **NOT** a third UMAP dimension. `umap_components` is always 2.
- **The desert field grid** is computed in 2D UMAP layout space (i.e., on the `[x, y]` plane).
- **Probe desert distances** are computed in the full high-D embedding space, not in the 2D layout.
- **`coordinates_2d`** in the journal stores the UMAP layout position `[x, y]`.
- **`coordinates_highD`** in the journal stores the original high-dimensional embedding vector.

These are different things measured in different spaces. Never conflate them. The distance between two concepts in 2D layout space is not the same as their distance in high-D embedding space.

## 3. Coordinate Systems

Three distinct coordinate systems exist simultaneously:

**a) High-D embedding space**
The raw output of the sentence-transformer model (typically 384d or 768d, reduced to 256d by PCA before UMAP). Used for: probe distance measurements, desert value computation on probes, cross-category probing. Stored in: `coordinates_highD` (null for `v1_import` entries).

**b) 2D UMAP layout space**
The 2D projection produced by UMAP with `UMAP_RANDOM_SEED = 42`. Used for: terrain layout, desert field grid positions, journal `coordinates_2d`, concept `position_2d`. This is the coordinate system all journal entries live in.

**c) Three.js scene space (`x`, `y`, `z`)**
The 3D space rendered in the browser. Derived from the 2D UMAP layout: `x` and `y` come from `position_2d`, `z` comes from the KDE density heightfield at that `[x, y]` position. This coordinate system exists only in the frontend renderer.

When a user clicks a point in the Three.js scene, the frontend must project back from scene `(x, y)` to UMAP `[x, y]` before writing `coordinates_2d` to the journal.

## 4. The UMAP Seed Invariant

```python
UMAP_RANDOM_SEED = 42  # scripts/terrain_config.py
```

This seed **must not change** after the first embedding run. Every journal entry's `coordinates_2d` is a position on the terrain produced by this specific seed. If the seed changes, the terrain layout changes, and all stored coordinates point to the wrong locations.

**V2 seed history:** V1 used seed 21, after two prior changes (42 → 1729 → 21). V2 restores 42 as the documented canonical value.

**If a seed change is ever necessary:**
1. Increment `SCHEMA_VERSION` in `terrain_config.py`.
2. Re-run the full pipeline to produce the new terrain.
3. Write a coordinate migration script that transforms all journal `coordinates_2d` from old-terrain positions to new-terrain positions using the inverse UMAP map or nearest-neighbor remapping.
4. Only then change the seed.

## 5. Journal Storage Invariant

**JSON is source of truth. SQLite is a derived read-optimized index.**

Rules — never violate these:
- **Never write directly to SQLite.**
- Always write JSON first, atomically: write to a temp file in the same directory, then `rename()` over the target. `rename()` is atomic on all supported platforms.
- After the JSON write succeeds, sync the SQLite index.
- SQLite is rebuilt automatically on startup if the index file is missing or its schema version does not match `INDEX_SCHEMA_VERSION`.
- `journal.json` is the backup target. The `.bak` file is written before any mass operation (import, migration, bulk delete).
- If `journal.json` is corrupted (invalid JSON or not an array), the server raises `RuntimeError` rather than silently dropping entries.

This invariant means the journal is always recoverable from `journal.json` alone. SQLite can be deleted and will be rebuilt.

## 6. Security Boundaries

**API key:** `ANTHROPIC_API_KEY` lives in `.env` only. It is read by the backend at startup. It never appears in client code, API responses, or logs.

**Rate limiting:** The `/api/describe-point` endpoint enforces a minimum interval of `LLM_RATE_LIMIT_INTERVAL_SECONDS` (3 seconds) between LLM calls. This is enforced at the backend, not the frontend, so it cannot be bypassed by a modified client.

**String sanitization:** All string inputs are sanitized on ingestion in `backend/app/models/journal.py` and in the migration script. Control characters (`0x00–0x08`, `0x0b`, `0x0c`, `0x0e–0x1f`, `0x7f`) are stripped. `<` and `>` are HTML-entity-encoded to `&lt;` and `&gt;`. LLM responses are additionally passed through `html.escape()` before being returned to the client.

**Path traversal:** Export and journal output paths are resolved with `Path.resolve()` and checked against the designated directory prefix before any file operation. Paths outside the allowed directory are rejected.

**CORS:** `allow_origins` is restricted to `localhost` only (`http://localhost:{PORT_FRONTEND}` and `http://127.0.0.1:3000`). Cross-origin requests from any other origin are rejected by the middleware.

**UUID parameters:** Entry IDs supplied in URL paths are capped at 36 characters before lookup, matching the UUID4 format length.

## 7. V1 Migration Notes

V1 journal entries migrated with `migrate_v1_journal.py` have these fixed values:

| Field | Value | Reason |
|---|---|---|
| `type` | `"v1_import"` | Identifies migrated entries |
| `roget_context` | `null` | V1 had no Roget taxonomy — cannot backfill |
| `coordinates_highD` | `null` | V1 did not store high-D vectors — cannot backfill |
| `v1_source` | original V1 entry | Preserved verbatim for auditability |

Migrated entries are full first-class journal entries and appear in all journal queries, filters, and exports. Their `null` `roget_context` means they cannot be filtered by Roget class unless manually tagged. If a V1 entry's `id` field exceeds 36 characters, a new UUID4 is generated; the original id is preserved in `v1_source`.
