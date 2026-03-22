"""
backend/app/config.py
Backend configuration. Imports constants from terrain_config.py and
adds backend-specific settings (paths, environment variables).
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR    = PROJECT_ROOT / "backend" / "data"
JOURNAL_DIR = DATA_DIR / "journal"
EXPORTS_DIR = DATA_DIR / "exports"

JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    PROJECT_VERSION, SCHEMA_VERSION,
    DESERT_GATE_THRESHOLD, DESERT_SHALLOW_THRESHOLD,
    LLM_MODEL, LLM_MAX_TOKENS,
    LLM_RATE_LIMIT_PER_HOUR, LLM_RATE_LIMIT_INTERVAL_SECONDS,
    MAX_QUERY_LENGTH, MAX_CONCEPT_LABEL_LENGTH, MAX_USER_NOTE_LENGTH,
    MAX_TAG_LENGTH, MAX_TAGS_PER_ENTRY, MAX_JOURNAL_ENTRIES,
    JOURNAL_FILENAME, JOURNAL_INDEX_FILENAME, JOURNAL_BACKUP_SUFFIX,
    PROBE_STEPS, SYNONYM_FILTER_COSINE,
    PROBE_PERCENTILE_LOW, PROBE_PERCENTILE_HIGH,
)

ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY")
PORT_BACKEND:  int = int(os.environ.get("PORT_BACKEND", "8000"))
PORT_FRONTEND: int = int(os.environ.get("PORT_FRONTEND", "3000"))
CORS_ORIGINS: list[str] = [
    f"http://localhost:{PORT_FRONTEND}",
    "http://127.0.0.1:3000",
]
