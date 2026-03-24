"""
probe_lib.py
Core probe computation library. No web framework dependencies.

Used by:
  - batch_cross_discover.py (CLI)
  - backend/app/services/probe_service.py (FastAPI)

The EmbeddingIndex class loads base embeddings once and builds a
KD-tree for fast nearest-neighbour search in high-D space.

Desert values returned by probes are measured in 384d embedding space.
This is different from the 2D grid desert field (which is in UMAP space).
Both measurements are valid and serve different purposes:
  - Probe desert (this module): genuine high-D measurement, used for
    discovery gating and field journal recording.
  - Grid desert (desert_field.npz): 2D approximation, used for
    terrain visualization and dig site enumeration.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.spatial import cKDTree

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import (
    PROBE_STEPS,
    SYNONYM_FILTER_COSINE,
    PROBE_PERCENTILE_LOW,
    PROBE_PERCENTILE_HIGH,
    PROBE_DESERT_GATE_THRESHOLD,
    PROBE_DESERT_SHALLOW_THRESHOLD,
    MAX_CONCEPT_LABEL_LENGTH,
    PROBE_INTERIOR_MIN,
    PROBE_INTERIOR_MAX,
)


@dataclass
class ProbeStep:
    step_index:       int
    alpha:            float           # interpolation parameter [0, 1]
    position_highD:   list[float]     # 384d vector (as list for JSON serialisation)
    nearest_term:     str
    nearest_distance: float           # Euclidean distance in 384d space
    desert_value:     float           # same as nearest_distance (named for clarity)
    nearest_concepts: list[dict]      # top-3 nearest [{term, distance, category_id}]


@dataclass
class ProbeResult:
    term_a:          str
    term_b:          str
    category_id_a:   Optional[str]
    category_id_b:   Optional[str]
    class_id_a:      Optional[int]
    class_id_b:      Optional[int]
    n_steps:         int
    steps:           list[ProbeStep]
    deepest_step:        ProbeStep
    desert_max:          float
    desert_mean:         float
    is_deep:             bool    # desert_max >= PROBE_DESERT_GATE_THRESHOLD
    is_shallow:          bool    # PROBE_DESERT_GATE_THRESHOLD <= desert_max < PROBE_DESERT_SHALLOW_THRESHOLD
    interior_steps_only: bool = True
    measurement_space:   str  = "384d embedding space"


class EmbeddingIndex:
    """
    Loads base embeddings and builds a KD-tree for high-D nearest-neighbour queries.
    Intended as a singleton -- build once, query many times.

    Thread-safety: KD-tree queries are read-only and thread-safe.
    Building the index is not thread-safe -- call build() at startup.
    """

    def __init__(self):
        self._built        = False
        self._terms:       list[str]         = []
        self._embeddings:  np.ndarray        = np.empty((0, 384))
        self._tree:        Optional[cKDTree] = None
        self._term_to_idx: dict[str, int]    = {}
        self._concept_meta: dict[str, dict]  = {}

    def build(
        self,
        embeddings_npz: Path,
        bundle_json:    Path,
    ) -> None:
        """
        Load embeddings and concept metadata. Build KD-tree.
        embeddings_npz: base_embeddings.npz
        bundle_json:    data_bundle.json (for Roget metadata per term)
        """
        print(f"Loading embeddings from {embeddings_npz} ...")
        data           = np.load(embeddings_npz, allow_pickle=True)
        raw_terms      = list(data["terms"])
        raw_embeddings = data["embeddings"].astype(np.float32)

        # Load concept metadata from bundle for Roget context
        concept_meta: dict[str, dict] = {}
        if bundle_json.exists():
            with open(bundle_json, encoding="utf-8") as f:
                bundle = json.load(f)
            for c in bundle.get("concepts", []):
                concept_meta[c["label"]] = {
                    "category_id":   c["roget_category_id"],
                    "category_name": c["roget_category_name"],
                    "section_name":  c["roget_section_name"],
                    "class_id":      c["roget_class_id"],
                    "class_name":    c["roget_class_name"],
                }

        # Keep only terms that have metadata (bundle is authoritative).
        # Fall back to all terms if bundle is empty.
        if concept_meta:
            keep_mask        = np.array([t in concept_meta for t in raw_terms])
            self._terms      = [t for t, k in zip(raw_terms, keep_mask) if k]
            self._embeddings = raw_embeddings[keep_mask]
        else:
            self._terms      = raw_terms
            self._embeddings = raw_embeddings

        self._term_to_idx  = {t: i for i, t in enumerate(self._terms)}
        self._concept_meta = concept_meta

        print(f"Building KD-tree over {len(self._terms):,} terms x "
              f"{self._embeddings.shape[1]}d ...")
        self._tree  = cKDTree(self._embeddings)
        self._built = True
        print("EmbeddingIndex ready.")

    @property
    def built(self) -> bool:
        return self._built

    def get_embedding(self, term: str) -> Optional[np.ndarray]:
        idx = self._term_to_idx.get(term)
        if idx is None:
            return None
        return self._embeddings[idx]

    def get_meta(self, term: str) -> dict:
        return self._concept_meta.get(term, {})

    def nearest_k(
        self,
        vector:        np.ndarray,
        k:             int = 3,
        exclude_terms: Optional[set[str]] = None,
    ) -> list[dict]:
        """
        Return the k nearest named concepts to a high-D vector.
        Returns list of {term, distance, category_id, category_name, class_id}.
        """
        if not self._built:
            raise RuntimeError("EmbeddingIndex not built.")
        k_query   = min(k + (len(exclude_terms) if exclude_terms else 0) + 5,
                        len(self._terms))
        distances, indices = self._tree.query(vector.reshape(1, -1), k=k_query)
        distances = distances[0]
        indices   = indices[0]

        results = []
        for dist, idx in zip(distances, indices):
            if idx >= len(self._terms):
                continue
            term = self._terms[idx]
            if exclude_terms and term in exclude_terms:
                continue
            meta = self._concept_meta.get(term, {})
            results.append({
                "term":          term,
                "distance":      float(dist),
                "category_id":   meta.get("category_id"),
                "category_name": meta.get("category_name"),
                "class_id":      meta.get("class_id"),
                "class_name":    meta.get("class_name"),
            })
            if len(results) >= k:
                break
        return results

    def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na < 1e-8 or nb < 1e-8:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def all_terms(self) -> list[str]:
        return self._terms

    def terms_in_category(self, category_id: str) -> list[str]:
        return [
            t for t, m in self._concept_meta.items()
            if m.get("category_id") == category_id
        ]

    def terms_in_class(self, class_id: int) -> list[str]:
        return [
            t for t, m in self._concept_meta.items()
            if m.get("class_id") == class_id
        ]


def run_probe(
    index:   "EmbeddingIndex",
    term_a:  str,
    term_b:  str,
    n_steps: int = PROBE_STEPS,
) -> Optional[ProbeResult]:
    """
    Run a probe between two named terms in high-D embedding space.

    Walks n_steps steps from term_a to term_b via linear interpolation
    in 384d space. At each step, finds the nearest named concept and
    records the distance.

    Returns None if either term is not in the index.

    Desert values are in 384d Euclidean distance units.
    These are NOT normalized -- raw distances are more interpretable
    for comparison across probes.
    """
    vec_a = index.get_embedding(term_a)
    vec_b = index.get_embedding(term_b)
    if vec_a is None or vec_b is None:
        return None

    meta_a  = index.get_meta(term_a)
    meta_b  = index.get_meta(term_b)
    exclude = {term_a, term_b}  # Don't report the endpoints as nearest

    steps: list[ProbeStep] = []
    for i in range(n_steps):
        alpha = i / max(n_steps - 1, 1)
        vec   = (1 - alpha) * vec_a + alpha * vec_b

        # Normalize to unit sphere before querying the KD-tree.
        # Linear interpolation between unit vectors produces a sub-unit
        # midpoint (norm < 1). Without normalization, L2 distances to
        # unit-norm neighbors are inflated and incomparable to V1 values.
        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec = vec / norm

        nearest = index.nearest_k(vec, k=3, exclude_terms=exclude)
        if not nearest:
            continue

        steps.append(ProbeStep(
            step_index=       i,
            alpha=            alpha,
            position_highD=   vec.tolist(),
            nearest_term=     nearest[0]["term"],
            nearest_distance= nearest[0]["distance"],
            desert_value=     nearest[0]["distance"],
            nearest_concepts= nearest,
        ))

    if not steps:
        return None

    # Interior steps only: exclude the endpoint neighbourhood.
    # Steps near alpha=0 (term_a) or alpha=1 (term_b) measure endpoint
    # sparsity, not the cross-domain gap. The interesting region is
    # the interior of the probe path.
    interior_steps = [
        s for s in steps
        if PROBE_INTERIOR_MIN <= s.alpha <= PROBE_INTERIOR_MAX
    ]

    # Fall back to all steps if the interior is empty (very short probes)
    scoring_steps = interior_steps if interior_steps else steps

    deepest = max(scoring_steps, key=lambda s: s.desert_value)
    d_max   = deepest.desert_value
    d_mean  = float(np.mean([s.desert_value for s in scoring_steps]))

    return ProbeResult(
        term_a=              term_a,
        term_b=              term_b,
        category_id_a=       meta_a.get("category_id"),
        category_id_b=       meta_b.get("category_id"),
        class_id_a=          meta_a.get("class_id"),
        class_id_b=          meta_b.get("class_id"),
        n_steps=             len(steps),
        steps=               steps,
        deepest_step=        deepest,
        desert_max=          d_max,
        desert_mean=         d_mean,
        is_deep=             d_max >= PROBE_DESERT_GATE_THRESHOLD,
        is_shallow=          PROBE_DESERT_GATE_THRESHOLD <= d_max < PROBE_DESERT_SHALLOW_THRESHOLD,
        interior_steps_only= len(interior_steps) > 0,
    )


def probe_result_to_dict(result: ProbeResult) -> dict:
    """Serialise ProbeResult to a JSON-safe dict."""
    def step_to_dict(s: ProbeStep) -> dict:
        return {
            "step_index":       s.step_index,
            "alpha":            s.alpha,
            "nearest_term":     s.nearest_term,
            "nearest_distance": s.nearest_distance,
            "desert_value":     s.desert_value,
            "nearest_concepts": s.nearest_concepts,
            # position_highD omitted from API responses (large, not needed by frontend)
        }

    return {
        "term_a":             result.term_a,
        "term_b":             result.term_b,
        "category_id_a":      result.category_id_a,
        "category_id_b":      result.category_id_b,
        "class_id_a":         result.class_id_a,
        "class_id_b":         result.class_id_b,
        "n_steps":             result.n_steps,
        "desert_max":          result.desert_max,
        "desert_mean":         result.desert_mean,
        "is_deep":             result.is_deep,
        "is_shallow":          result.is_shallow,
        "interior_steps_only": result.interior_steps_only,
        "measurement_space":   result.measurement_space,
        "deepest_step_index": result.deepest_step.step_index,
        "deepest_step":       step_to_dict(result.deepest_step),
        "steps":              [step_to_dict(s) for s in result.steps],
    }
