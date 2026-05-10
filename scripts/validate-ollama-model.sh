#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[validate-ollama-model] %s\n' "$*"; }
fail() { printf '[validate-ollama-model] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/validate-ollama-model.sh [--smoke-test]

Validate that the configured Ollama model is already available offline.
Environment:
  OLLAMA_URL    Ollama API URL (default: http://localhost:11434)
  OLLAMA_MODEL  Expected model (default: mistral)
USAGE
}

smoke_test=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke-test) smoke_test=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

ollama_url="${OLLAMA_URL:-http://localhost:11434}"
model="${OLLAMA_MODEL:-mistral}"

tags_json="$(mktemp)"
cleanup() { rm -f "$tags_json"; }
trap cleanup EXIT

log "Checking Ollama tags at ${ollama_url}/api/tags"
if ! curl -fsS "${ollama_url%/}/api/tags" > "$tags_json"; then
  fail "could not reach Ollama at ${ollama_url}; start the ollama service and retry"
fi

if ! python3 - "$tags_json" "$model" <<'PY'
from __future__ import annotations
import json
import sys
path, expected = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
models = data.get("models", [])
names = {item.get("name", "") for item in models if isinstance(item, dict)}
expected_with_tag = expected if ":" in expected.split("/")[-1] else f"{expected}:latest"
if expected not in names and expected_with_tag not in names:
    print("Configured model is missing.", file=sys.stderr)
    print(f"Expected: {expected} or {expected_with_tag}", file=sys.stderr)
    print("Available: " + (", ".join(sorted(names)) or "<none>"), file=sys.stderr)
    sys.exit(1)
PY
then
  fail "configured OLLAMA_MODEL is not available offline: $model"
fi
log "Configured model is available offline: $model"

if [[ "$smoke_test" -eq 1 ]]; then
  response_json="$(mktemp)"
  trap 'rm -f "$tags_json" "$response_json"' EXIT
  log "Running local generation smoke test (no pull/download)"
  payload="$(python3 - "$model" <<'PY'
from __future__ import annotations
import json, sys
print(json.dumps({"model": sys.argv[1], "prompt": "Reply with OK.", "stream": False, "options": {"num_predict": 8}}))
PY
)"
  if ! curl -fsS -H 'Content-Type: application/json' -d "$payload" "${ollama_url%/}/api/generate" > "$response_json"; then
    fail "Ollama generation smoke test failed for model: $model"
  fi
  if ! python3 - "$response_json" <<'PY'
from __future__ import annotations
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
response = str(data.get("response", "")).strip()
if not response:
    print("empty Ollama generation response", file=sys.stderr)
    sys.exit(1)
PY
  then
    fail "Ollama smoke test returned an empty response"
  fi
  log "Smoke test passed"
fi

log "Ollama model validation passed"
