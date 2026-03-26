# run_pipeline.ps1
# Full pipeline automation for Latent Language Explorer V2
#
# Usage:
#   .\run_pipeline.ps1                   Run full pipeline
#   .\run_pipeline.ps1 -Downstream       Skip vocabulary rebuild

param([switch]$Downstream)
$ErrorActionPreference = "Stop"
$sw = [System.Diagnostics.Stopwatch]::StartNew()

function Step($n, $desc, $script) {
    Write-Host "[$n] $desc..."
    py $script
}

if (-not $Downstream) {
    Write-Host "=== Vocabulary Pipeline ==="
    Step "1/6" "Parsing Roget taxonomy"   "scripts/parse_roget.py"
    Step "2/6" "Filtering vocabulary"      "scripts/filter_vocab.py"
    Step "3/6" "WordNet enrichment"        "scripts/enrich_wordnet.py"
    Step "4/6" "Modern domain supplements" "scripts/add_modern_domains.py"
    Step "5/6" "Building vocab index"      "scripts/build_vocab_index.py"
    Step "6/6" "Validating vocabulary"     "scripts/validate_vocab.py"
}

Write-Host ""
Write-Host "=== Embedding Pipeline ==="
Step "1/10" "Base embeddings"           "scripts/compute_base_embeddings.py"
Step "2/10" "Contextual embeddings"     "scripts/compute_contextual_embeddings.py"
Step "3/10" "UMAP projection"           "scripts/compute_umap.py"
Step "4/10" "Context positions"         "scripts/compute_context_positions.py"
Step "5/10" "Density field"             "scripts/compute_density.py"
Step "6/10" "Gradient field"            "scripts/compute_gradients.py"
Step "7/10" "Attractors"                "scripts/compute_attractors.py"
py scripts/compute_basins.py
Step "8/10" "Desert field"              "scripts/compute_desert_field.py"
Step "9/10" "Assembling data bundle"    "scripts/assemble_bundle.py"

Write-Host ""
Write-Host "=== Discovery Data ==="
Step "1/2" "Dig site enumeration"      "scripts/find_dig_sites.py"
Step "2/2" "Voronoi decomposition"     "scripts/compute_voronoi.py"

$sw.Stop()
Write-Host ""
Write-Host ("Pipeline complete in {0:mm\:ss}" -f $sw.Elapsed)
Write-Host "Start the application: .\start.ps1"
