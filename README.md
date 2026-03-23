# Latent Language Explorer V2

Semantic meaning exists in embedding space that lacks syntactic representation in natural language — concepts that shape thought and craft but resist naming. This project finds those gaps, measures them, describes them, and materializes them as physical art. It maps a vocabulary derived from Roget's 1911 Thesaurus through contextual sentence-transformer embeddings, reduces the resulting high-dimensional space to a navigable 2D terrain, and exposes the desert regions between named concepts — the places where meaning lives without words. Those regions can be probed, journaled, and decoded via LLM, then exported as heightfield data for CNC milling, laser etching, or 3D printing.

## Quick Start

```bash
# Install dependencies
./start.sh --install        # Mac/Linux
.\start.ps1 -Install        # Windows

# Start both servers
./start.sh                  # Mac/Linux
.\start.ps1                 # Windows
```

- Backend: http://localhost:8000/api/docs
- Frontend: http://localhost:3000

## Architecture

TypeScript + React + Vite frontend with a Three.js 3D terrain viewer and Zustand state management. FastAPI Python backend handles journal persistence, LLM proxying, and terrain data serving. Sentence-transformers generate contextual embeddings using six Roget-class template sentences per term. Roget's Thesaurus (1911) provides the taxonomic backbone — six classes, ~1,000 categories — enriched with WordNet for modern vocabulary coverage.

## Project Structure

```
frontend/   TypeScript + React + Vite application
backend/    FastAPI server, journal storage, LLM proxy
scripts/    Data pipeline scripts (run manually, no HTTP)
data/       Schemas and pipeline outputs (large files gitignored)
docs/       Architecture and data format documentation
```

## Pipeline Status

As of Phase 0 the data pipeline has not yet run. All terrain endpoints (`/api/concepts`, `/api/terrain`, `/api/desert-field`, etc.) return **501 Not Implemented** with a message indicating the pipeline must be run first. Journal endpoints are fully operational. See `docs/` for pipeline documentation when available.

## V1 Journal Migration

If you have a V1 journal export (from the V1 localStorage export function), migrate it **before** creating any V2 entries:

```bash
py scripts/migrate_v1_journal.py \
   --input path/to/v1_journal.json \
   --output backend/data/journal/journal.json
```

Use `--dry-run` to validate without writing. Use `--force` to overwrite an existing V2 journal.

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Required for generative decoding (optional otherwise) |
| `PORT_BACKEND` | Backend port (default: 8000) |
| `PORT_FRONTEND` | Frontend dev port (default: 3000) |

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

## UMAP Seed

The UMAP random seed is **42**, defined in `scripts/terrain_config.py`. **Do not change this after the first embedding run.** Changing the seed invalidates all journal `coordinates_2d` values. If a seed change is ever necessary, increment `SCHEMA_VERSION` in `terrain_config.py` and write a coordinate migration script before touching the seed.
