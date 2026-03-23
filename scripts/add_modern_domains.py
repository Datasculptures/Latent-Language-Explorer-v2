"""
add_modern_domains.py
Add curated modern domain vocabulary to the enriched Roget taxonomy.

Modern domains address post-1911 fields that Roget's 1911 edition lacks.
Terms are added to the nearest thematic Roget category and tagged
is_modern_addition: true so they can be filtered or highlighted.

The parent_category_name fields below must be matched against actual
category names in roget_enriched.json. The match_category() function
finds the best match — review its output to verify correct placement.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE   = PROJECT_ROOT / "data" / "roget" / "roget_enriched.json"
OUTPUT_FILE  = PROJECT_ROOT / "data" / "roget" / "roget_modern.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from terrain_config import VOCAB_MODERN_DOMAIN_TERM_CAP

# ── Modern domain term lists ───────────────────────────────────────────────
# Each domain: name, parent category hint, terms.
# Terms are lowercase single words. No phrases.
# Capped at VOCAB_MODERN_DOMAIN_TERM_CAP (100) per domain.

MODERN_DOMAINS = [
    {
        "domain_name": "Artificial Intelligence",
        "domain_tag":  "AI",
        "parent_category_hint": "Intellect",  # Will be matched to nearest Roget category
        "terms": [
            # Core ML concepts
            "gradient", "backpropagation", "epoch", "batch", "dropout",
            "regularization", "overfitting", "underfitting", "hyperparameter",
            "tokenization", "embedding", "transformer", "attention", "encoder",
            "decoder", "autoencoder", "diffusion", "denoising", "finetuning",
            "pretraining", "inference", "hallucination", "grounding", "alignment",
            "reward", "policy", "rollout", "exploration", "exploitation",
            "adversarial", "perturbation", "robustness", "calibration",
            "benchmark", "evaluation", "ablation", "baseline", "checkpoint",
            "dataset", "annotation", "labeling", "preprocessing", "augmentation",
            "pruning", "quantization", "distillation", "compression", "latency",
            "throughput", "deployment", "serving", "pipeline", "workflow",
            "prompt", "context", "retrieval", "generation", "classification",
            "regression", "clustering", "segmentation", "detection", "recognition",
            "summarization", "translation", "reasoning", "planning", "memory",
            "agency", "tool", "multimodal", "vision", "speech", "language",
            "representation", "disentanglement", "interpolation", "extrapolation",
            "generalization", "transfer", "adaptation", "catastrophic", "forgetting",
            "convergence", "divergence", "loss", "accuracy", "precision",
            "recall", "confidence", "uncertainty", "entropy", "perplexity",
        ][:VOCAB_MODERN_DOMAIN_TERM_CAP],
    },
    {
        "domain_name": "Computing",
        "domain_tag":  "CS",
        "parent_category_hint": "Instrumentality",
        "terms": [
            # Core CS concepts
            "algorithm", "recursion", "iteration", "abstraction", "encapsulation",
            "polymorphism", "inheritance", "interface", "protocol", "serialization",
            "deserialization", "parsing", "compilation", "interpretation", "linking",
            "debugging", "profiling", "optimization", "refactoring", "testing",
            "mocking", "caching", "indexing", "hashing", "encryption", "decryption",
            "authentication", "authorization", "middleware", "containerization",
            "virtualization", "orchestration", "provisioning", "deployment",
            "scalability", "availability", "reliability", "observability",
            "telemetry", "logging", "monitoring", "tracing", "alerting",
            "concurrency", "parallelism", "threading", "asynchrony", "blocking",
            "nonblocking", "streaming", "buffering", "throttling", "backpressure",
            "idempotency", "atomicity", "consistency", "isolation", "durability",
            "replication", "partitioning", "sharding", "federation", "migration",
            "versioning", "schema", "query", "transaction", "rollback", "commit",
            "networking", "routing", "switching", "tunneling", "proxying",
            "compression", "encoding", "decoding", "transformation", "validation",
            "sanitization", "rendering", "layout", "typography", "accessibility",
        ][:VOCAB_MODERN_DOMAIN_TERM_CAP],
    },
    {
        "domain_name": "Molecular Biology",
        "domain_tag":  "BIO",
        "parent_category_hint": "Life",
        "terms": [
            # Core molecular biology concepts
            "genome", "proteome", "transcriptome", "metabolome", "epigenome",
            "chromosome", "plasmid", "ribosome", "mitochondria", "chloroplast",
            "nucleotide", "nucleoside", "phospholipid", "glycoprotein", "liposome",
            "transcription", "translation", "replication", "recombination",
            "mutation", "deletion", "insertion", "substitution", "duplication",
            "amplification", "sequencing", "alignment", "assembly", "annotation",
            "expression", "regulation", "repression", "activation", "inhibition",
            "phosphorylation", "methylation", "acetylation", "ubiquitination",
            "splicing", "editing", "silencing", "interference", "knockdown",
            "knockout", "overexpression", "transfection", "transformation",
            "cloning", "ligation", "digestion", "hybridization", "immunoprecipitation",
            "electrophoresis", "chromatography", "centrifugation", "microscopy",
            "immunofluorescence", "cytometry", "proteomics", "genomics",
            "bioinformatics", "pathway", "network", "cascade", "feedback",
            "homeostasis", "differentiation", "proliferation", "apoptosis",
            "senescence", "stemness", "plasticity", "epigenetics", "heritability",
        ][:VOCAB_MODERN_DOMAIN_TERM_CAP],
    },
    {
        "domain_name": "Cognitive Science",
        "domain_tag":  "COG",
        "parent_category_hint": "Intellect",
        "terms": [
            # Core cognitive science concepts
            "cognition", "metacognition", "perception", "attention", "salience",
            "awareness", "consciousness", "qualia", "phenomenology", "intentionality",
            "working", "episodic", "semantic", "procedural", "declarative",
            "retrieval", "consolidation", "reconsolidation", "forgetting",
            "priming", "interference", "chunking", "schema", "heuristic",
            "bias", "anchoring", "framing", "availability", "representativeness",
            "satisficing", "rationality", "bounded", "embodiment", "enaction",
            "affordance", "proprioception", "interoception", "exteroception",
            "affect", "valence", "arousal", "appraisal", "regulation",
            "empathy", "mentalizing", "mirroring", "imitation", "learning",
            "conditioning", "reinforcement", "prediction", "expectation",
            "surprise", "uncertainty", "inference", "categorization", "abstraction",
            "analogy", "metaphor", "narrative", "simulation", "imagination",
            "creativity", "insight", "fluency", "flexibility", "originality",
            "lateralization", "plasticity", "development", "aging", "rehabilitation",
        ][:VOCAB_MODERN_DOMAIN_TERM_CAP],
    },
]


def match_category(data: dict, hint: str) -> dict | None:
    """
    Find the best matching category in the hierarchy for a given hint.
    Returns the category dict or None.
    Simple substring match on category name — case-insensitive.
    """
    hint_lower = hint.lower()
    best: dict | None = None
    for cls in data["classes"]:
        for sec in cls["sections"]:
            for cat in sec["categories"]:
                if hint_lower in cat["name"].lower():
                    # Prefer shorter name matches (more specific)
                    if best is None or len(cat["name"]) < len(best["name"]):
                        best = cat
    return best


def make_modern_term(term: str) -> dict:
    return {
        "term":                  term,
        "original":              term,
        "obsolete":              False,
        "flagged_proper_noun":   False,
        "kept":                  True,
        "wordnet_enriched":      False,
        "is_modern_addition":    True,
    }


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run enrich_wordnet.py first.")
        sys.exit(1)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_added = 0
    placement_report = []

    for domain in MODERN_DOMAINS:
        hint    = domain["parent_category_hint"]
        cat     = match_category(data, hint)
        added   = 0

        if cat is None:
            print(f"WARNING: No category match for hint '{hint}' (domain: {domain['domain_name']})")
            print("  Review category names in roget_enriched.json and update the hint.")
            placement_report.append({
                "domain": domain["domain_name"],
                "hint": hint,
                "matched_category": None,
                "terms_added": 0,
                "error": "no_match",
            })
            continue

        # Get existing terms in this category
        existing = {
            w["term"] for w in cat["words"]
            if isinstance(w, dict) and w.get("kept", False)
        }

        for term in domain["terms"]:
            if term not in existing:
                cat["words"].append(make_modern_term(term))
                existing.add(term)
                added += 1

        total_added += added
        placement_report.append({
            "domain":            domain["domain_name"],
            "domain_tag":        domain["domain_tag"],
            "hint":              hint,
            "matched_category":  cat["name"],
            "matched_category_id": cat["id"],
            "terms_added":       added,
        })
        print(f"  {domain['domain_name']}: +{added} terms -> [{cat['id']}] {cat['name']}")

    # Update meta
    data["meta"]["modern_domains_added"] = len(MODERN_DOMAINS)
    data["meta"]["modern_terms_added"]   = total_added
    data["meta"]["modern_timestamp"]     = datetime.now(timezone.utc).isoformat()

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nModern domain summary:")
    for r in placement_report:
        print(f"  {r['domain']}: {r['terms_added']} terms -> {r.get('matched_category', 'NO MATCH')}")
    print(f"\nTotal modern terms added: {total_added}")
    print(f"Wrote: {OUTPUT_FILE}")

    # Warn if any domain had no match
    unmatched = [r for r in placement_report if r.get("error") == "no_match"]
    if unmatched:
        print(f"\nACTION REQUIRED: {len(unmatched)} domain(s) had no category match.")
        print("Update parent_category_hint values in add_modern_domains.py to match")
        print("actual category names found in roget_enriched.json.")


if __name__ == "__main__":
    main()
