"""
terrain_config.py
Single source of truth for all pipeline and configuration constants.
Latent Language Explorer V2

CRITICAL: Do not change UMAP_RANDOM_SEED after the first embedding run.
Changing the seed invalidates all journal coordinates. If the seed must
change, increment SCHEMA_VERSION and write a coordinate migration script.
"""

# ── Versioning ────────────────────────────────────────────────────────
PROJECT_VERSION = "2.0.0"
SCHEMA_VERSION = 1

# ── UMAP ──────────────────────────────────────────────────────────────
# Seed 42. Do not change after first embedding run.
# V1 used seed 21 (after two prior changes: 42 → 1729 → 21).
# V2 restores 42 as the documented canonical value.
UMAP_RANDOM_SEED = 42
UMAP_N_COMPONENTS = 2       # 2D layout. Height is KDE density, not a UMAP dim.
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1

# ── PCA pre-reduction ─────────────────────────────────────────────────
PCA_N_COMPONENTS = 256

# ── Desert field ──────────────────────────────────────────────────────
# NOTE: The desert field grid is computed in 2D UMAP space (not high-D).
# Desert values on probes are computed in the full high-D embedding space.
# These are different measurements. Both are valid. Document this.
DESERT_FIELD_RESOLUTION = 128
DESERT_FIELD_MAX_RESOLUTION = 1024
DESERT_GATE_THRESHOLD = 0.02
DESERT_SHALLOW_THRESHOLD = 0.05
DESERT_DIG_SITE_THRESHOLD = 0.65
DESERT_DIG_SITE_MIN_CELLS = 8

# ── Cross-domain probing ───────────────────────────────────────────────
PROBE_STEPS = 30
PROBE_PERCENTILE_LOW = 40
PROBE_PERCENTILE_HIGH = 75
SYNONYM_FILTER_COSINE = 0.85

# ── Generative decoding ────────────────────────────────────────────────
LLM_MODEL = "claude-haiku-4-5"
LLM_MAX_TOKENS = 150
LLM_RATE_LIMIT_PER_HOUR = 60
LLM_RATE_LIMIT_INTERVAL_SECONDS = 3

# ── Vocabulary ─────────────────────────────────────────────────────────
VOCAB_MIN_TERM_LENGTH = 4
VOCAB_WORDNET_HOP_DEPTH = 1
VOCAB_MODERN_DOMAIN_CAP = 4
VOCAB_MODERN_DOMAIN_TERM_CAP = 100

# ── Fabrication export ─────────────────────────────────────────────────
EXPORT_DEFAULT_GRID_SIZE = 48
EXPORT_DEFAULT_BASE_INCHES = 12.0
EXPORT_DEFAULT_MAX_HEIGHT_INCHES = 6.0
EXPORT_CONTOUR_INTERVAL_INCHES = 0.25
EXPORT_DPI = 300
EXPORT_MAX_GRID_DIMENSION = 1024

# ── Security ───────────────────────────────────────────────────────────
MAX_QUERY_LENGTH = 500
MAX_CONCEPT_LABEL_LENGTH = 100
MAX_USER_NOTE_LENGTH = 2000
MAX_TAG_LENGTH = 50
MAX_TAGS_PER_ENTRY = 20
MAX_JOURNAL_ENTRIES = 50000

# ── Field journal ──────────────────────────────────────────────────────
JOURNAL_FILENAME = "journal.json"
JOURNAL_INDEX_FILENAME = "journal.db"
JOURNAL_BACKUP_SUFFIX = ".bak"

# ── Contextual embedding templates ────────────────────────────────────
# One template per Roget Class (6 classes) plus neutral.
# Used in Phase 2 to generate multi-context embeddings.
# {term} is the placeholder.
CONTEXT_TEMPLATES = {
    "abstract_relations": "The concept of {term} involves fundamental relationships between ideas, properties, and existence.",
    "space":              "In spatial terms, {term} describes a quality of physical arrangement, form, or position.",
    "matter":             "As a material phenomenon, {term} relates to the physical substance or sensory experience of the world.",
    "intellect":          "Intellectually, {term} is a concept involved in the formation or communication of ideas.",
    "volition":           "As an act of will, {term} describes something done deliberately, with intention or agency.",
    "affections":         "Emotionally or morally, {term} characterizes a feeling, disposition, or value held by a person.",
    "neutral":            "{term} is a concept that can be defined and distinguished from related ideas.",
}

# ── Roget class labels ─────────────────────────────────────────────────
ROGET_CLASSES = {
    1: "Abstract Relations",
    2: "Space",
    3: "Matter",
    4: "Intellect",
    5: "Volition",
    6: "Affections",
}

# ── Data bundle ────────────────────────────────────────────────────────
DATA_BUNDLE_VERSION = "2.0"
