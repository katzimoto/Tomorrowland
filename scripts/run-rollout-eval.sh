#!/usr/bin/env bash
set -euo pipefail

# Controlled rollout evaluation for #715 feature flags.
#
# Runs the offline eval harness with 4 configurations:
#   baseline     — both flags off (current default)
#   hierarchy    — hierarchy expansion only
#   coarse2fine  — coarse-to-fine routing only
#   combined     — both flags on
#
# Usage:
#   bash scripts/run-rollout-eval.sh [--output-dir ./eval-results]
#
# Requires: pytest with --eval, live Qdrant + Ollama + PostgreSQL.

OUTPUT_DIR="${1:-./eval-results}"
mkdir -p "$OUTPUT_DIR"

# Map Docker-internal hostnames to localhost so the test can reach services
# from the host.  Adjust if your services listen on different ports.
export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export POSTGRES_URL="${POSTGRES_URL:-postgresql+psycopg://postgres:tomorrowland-dev@localhost:5432/app}"

PYTEST_ARGS=(
  tests/eval/
  --eval
  --eval-output "$OUTPUT_DIR/results-baseline.json"
  -q
)

GLOBAL_EVAL_ARGS=(
  --eval
  -q
  --no-header
)

run_config() {
  local name="$1"
  local output="$OUTPUT_DIR/results-${name}.json"
  shift

  echo "========================================"
  echo "  Configuration: $name"
  echo "  Flags: $*"
  echo "  Output: $output"
  echo "========================================"

  # Unset all feature flags first, then set the ones we want
  export FEATURE_DOCUMENT_CHAT_HIERARCHY_EXPANSION=false
  export FEATURE_DOCUMENT_CHAT_COARSE_TO_FINE_ROUTING=false

  # Parse flag overrides like hierarchy=true coarse2fine=true
  while [ $# -gt 0 ]; do
    case "$1" in
      hierarchy=true)  export FEATURE_DOCUMENT_CHAT_HIERARCHY_EXPANSION=true ;;
      coarse2fine=true) export FEATURE_DOCUMENT_CHAT_COARSE_TO_FINE_ROUTING=true ;;
    esac
    shift
  done

  uv run pytest tests/eval/ "${GLOBAL_EVAL_ARGS[@]}" --eval-output "$output" 2>&1 \
    | tee "$OUTPUT_DIR/${name}.log"
  echo ""
}

echo "=== #715 Rollout Evaluation ==="
echo "Output directory: $OUTPUT_DIR"
date -u
echo ""

run_config "baseline"
run_config "hierarchy"    hierarchy=true
run_config "coarse2fine"  coarse2fine=true
run_config "combined"     hierarchy=true coarse2fine=true

echo "========================================"
echo "  All configurations complete."
echo "========================================"

# Generate comparison report
python3 scripts/compare-eval-runs.py \
  "$OUTPUT_DIR/results-baseline.json" \
  "$OUTPUT_DIR/results-hierarchy.json" \
  "$OUTPUT_DIR/results-coarse2fine.json" \
  "$OUTPUT_DIR/results-combined.json" \
  2>&1 | tee "$OUTPUT_DIR/comparison-report.txt"
