#!/usr/bin/env bash
# run_pipeline.sh
# Full pipeline automation for Latent Language Explorer V2
#
# Usage:
#   ./run_pipeline.sh                Run full pipeline
#   ./run_pipeline.sh --downstream   Skip vocabulary rebuild

set -euo pipefail

DOWNSTREAM=false
for arg in "$@"; do [[ "$arg" == "--downstream" ]] && DOWNSTREAM=true; done

start=$(date +%s)
step() { echo "[$1] $2..."; python3 "$3"; }

if [ "$DOWNSTREAM" = false ]; then
    echo "=== Vocabulary Pipeline ==="
    step "1/6" "Parsing Roget taxonomy"   scripts/parse_roget.py
    step "2/6" "Filtering vocabulary"      scripts/filter_vocab.py
    step "3/6" "WordNet enrichment"        scripts/enrich_wordnet.py
    step "4/6" "Modern domain supplements" scripts/add_modern_domains.py
    step "5/6" "Building vocab index"      scripts/build_vocab_index.py
    step "6/6" "Validating vocabulary"     scripts/validate_vocab.py
fi

echo ""
echo "=== Embedding Pipeline ==="
step "1/10" "Base embeddings"           scripts/compute_base_embeddings.py
step "2/10" "Contextual embeddings"     scripts/compute_contextual_embeddings.py
step "3/10" "UMAP projection"           scripts/compute_umap.py
step "4/10" "Context positions"         scripts/compute_context_positions.py
step "5/10" "Density field"             scripts/compute_density.py
step "6/10" "Gradient field"            scripts/compute_gradients.py
step "7/10" "Attractors"                scripts/compute_attractors.py
python3 scripts/compute_basins.py
step "8/10" "Desert field"              scripts/compute_desert_field.py
step "9/10" "Data bundle"               scripts/assemble_bundle.py

echo ""
echo "=== Discovery Data ==="
step "1/2" "Dig sites"   scripts/find_dig_sites.py
step "2/2" "Voronoi"     scripts/compute_voronoi.py

elapsed=$(( $(date +%s) - start ))
echo ""
echo "Pipeline complete in ${elapsed}s"
echo "Start: ./start.sh"
