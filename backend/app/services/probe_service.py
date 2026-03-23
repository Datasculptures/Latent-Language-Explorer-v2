"""
backend/app/services/probe_service.py
Singleton probe service wrapping EmbeddingIndex.
Built once at FastAPI startup, reused for all probe requests.
"""

import sys
from pathlib import Path

# Add scripts/ to path for probe_lib import
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from probe_lib import EmbeddingIndex, run_probe, probe_result_to_dict

_BASE_NPZ = PROJECT_ROOT / "data" / "embeddings" / "base_embeddings.npz"
_BUNDLE   = PROJECT_ROOT / "backend" / "data" / "data_bundle.json"

_index: EmbeddingIndex | None = None


def get_index() -> EmbeddingIndex | None:
    return _index


def build_index() -> bool:
    """
    Build the embedding index. Call from FastAPI lifespan startup.
    Returns True if built successfully, False if embeddings not available.
    """
    global _index
    if not _BASE_NPZ.exists():
        return False
    idx = EmbeddingIndex()
    idx.build(_BASE_NPZ, _BUNDLE)
    _index = idx
    return True


def probe(term_a: str, term_b: str, n_steps: int = 30) -> dict | None:
    """Run a probe. Returns serialised result dict or None."""
    if _index is None or not _index.built:
        return None
    result = run_probe(_index, term_a, term_b, n_steps=n_steps)
    if result is None:
        return None
    return probe_result_to_dict(result)
