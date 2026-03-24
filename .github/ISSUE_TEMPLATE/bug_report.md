---
name: Bug report
about: Report a reproducible problem with the pipeline, backend, or frontend
title: "[BUG] "
labels: bug
assignees: ''
---

## Description

A clear description of what is wrong and what you expected instead.

## Steps to reproduce

1.
2.
3.

## Environment

- OS:
- Python version (`py --version`):
- Node version (`node --version`):
- Browser (if frontend issue):

## Component

- [ ] Vocabulary pipeline (`scripts/parse_roget.py` … `validate_vocab.py`)
- [ ] Embedding pipeline (`compute_base_embeddings.py` … `assemble_bundle.py`)
- [ ] Discovery pipeline (`find_dig_sites.py`, `batch_cross_discover.py`)
- [ ] Backend API (`backend/app/main.py`)
- [ ] Frontend (Landscape / Discovery page)
- [ ] Fabrication export (`export_topo.py`, `export_stl.py`, `generate_instruction_sheet.py`)
- [ ] Field journal (read / write / SQLite)
- [ ] Other

## Error output

```
Paste the full traceback or console error here.
```

## Additional context

Any other relevant details (data file state, journal entry ID, probe pair, etc.).
