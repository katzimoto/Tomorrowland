#!/usr/bin/env bash
# scripts/dev/smoke_document_flow.sh
#
# CI-compatible document-flow smoke test.  Validates that the Tomorrowland API
# and frontend are reachable and responding correctly.  Designed for reuse by
# both local demo workflows and GitHub Actions (issue #547).
#
# Stages:
#   1. check_dependencies — curl, python3
#   2. api_health         — GET /health
#   3. frontend_health    — GET /health (skipped when FRONTEND_URL unset)
#  3b. mcp_health         — GET /mcp (MCP adapter reachability)
#   4. doc_bootstrap      — docker compose exec smoke_bootstrap (skip if Docker absent)
#   5. auth_login         — POST /auth/login (skipped when creds unset)
#   6. doc_ingest         — POST /admin/ingestion/{source}/sync-now + poll search
#   7. doc_search         — POST /search (extracts FIRST_DOC_ID for later stages)
#   8. doc_preview        — GET /preview/{id} (skipped when no doc available)
#   9. doc_text           — GET /documents/{id}/text (skipped when no doc available)
#  10. doc_download       — GET /download/{id} (skipped when no doc available)
#
# SMOKE_MODE=ci makes every stage a hard failure and writes machine-readable
# JSON to a deterministic path (default tmp/smoke-document-flow-result.json).

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_URL="${API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-}"
SMOKE_MODE="${SMOKE_MODE:-local}"
RESULT_FILE="${RESULT_FILE:-tmp/smoke-document-flow-result.json}"
TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-8}"
POLL_SECONDS="${SMOKE_POLL_SECONDS:-2}"

SMOKE_ADMIN_EMAIL="${SMOKE_ADMIN_EMAIL:-}"
SMOKE_ADMIN_PASSWORD="${SMOKE_ADMIN_PASSWORD:-}"
SMOKE_QUERY="${SMOKE_QUERY:-tomorrowland}"
SMOKE_DOCUMENT_ID="${SMOKE_DOCUMENT_ID:-}"
SMOKE_GROUP_NAME="${SMOKE_GROUP_NAME:-smoke-operators}"
SMOKE_SOURCE_NAME="${SMOKE_SOURCE_NAME:-smoke-folder-source}"
SMOKE_FIXTURE_DIR="${SMOKE_FIXTURE_DIR:-/data/smoke-fixtures}"
SMOKE_FIXTURE_NAME="${SMOKE_FIXTURE_NAME:-tomorrowland-smoke-document.txt}"

START_EPOCH="$(date +%s)"

STAGE_STATUS=""
HAS_FAILURE=0
AUTH_TOKEN=""
FIRST_DOC_ID=""
SOURCE_ID=""
CURL_JSON_HTTP_CODE=0
# File used to pass the HTTP status code out of the curl_json subshell.
_HTTP_CODE_FILE="${TMPDIR:-/tmp}/.smoke_http_code_$$"

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
usage() {
  cat <<'USAGE'
Usage: bash scripts/dev/smoke_document_flow.sh [OPTIONS]

Validate the Tomorrowland API and frontend document flow.

Options:
  -h, --help   Show this help text.

Environment:
  API_URL                  Default: http://localhost:8000
  FRONTEND_URL             Unset by default (frontend check skipped)
  SMOKE_MODE               local (default) or ci
                           ci mode: hard failures, deterministic result path
  RESULT_FILE              Default: tmp/smoke-document-flow-result.json
  SMOKE_TIMEOUT_SECONDS    Default: 8
  SMOKE_ADMIN_EMAIL        Required for auth_login stage
  SMOKE_ADMIN_PASSWORD     Required for auth_login stage
  SMOKE_QUERY              Default: tomorrowland
  SMOKE_DOCUMENT_ID        Bypass search; use this doc directly
  SMOKE_GROUP_NAME         Group for bootstrap fixtures (default: smoke-operators)
  SMOKE_SOURCE_NAME        Source name for bootstrap (default: smoke-folder-source)
  SMOKE_FIXTURE_DIR        Dir for bootstrap fixture (default: /data/smoke-fixtures)
  SMOKE_FIXTURE_NAME       Fixture filename (default: tomorrowland-smoke-document.txt)

Examples:
  # Local smoke check (frontend skipped, auth skipped)
  bash scripts/dev/smoke_document_flow.sh

  # Full local smoke with auth
  SMOKE_ADMIN_EMAIL=admin@example.com SMOKE_ADMIN_PASSWORD=secret \
    bash scripts/dev/smoke_document_flow.sh

  # CI smoke check with all services
  SMOKE_MODE=ci FRONTEND_URL=http://frontend:8080 \
    SMOKE_ADMIN_EMAIL=admin@example.com SMOKE_ADMIN_PASSWORD=secret \
    bash scripts/dev/smoke_document_flow.sh

  # Smoke against a known document (skip search-based discovery)
  SMOKE_DOCUMENT_ID=abc-123 \
    bash scripts/dev/smoke_document_flow.sh

  # Custom result path
  RESULT_FILE=/tmp/result.json \
    bash scripts/dev/smoke_document_flow.sh
USAGE
}

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log_step()  { echo "==> $*"; }
log_ok()    { echo "  [PASS] $*"; }
log_fail()  { echo "  [FAIL] $*" >&2; }
log_skip()  { echo "  [SKIP] $*"; }
log_info()  { echo "  [INFO] $*"; }

warn_logs() {
  echo "" >&2
  echo "Useful next commands:" >&2
  echo "  docker compose logs --tail=100 api frontend" >&2
  echo "  docker compose ps" >&2
  echo "  curl -sf ${API_URL}/health" >&2
  if [[ -n "$FRONTEND_URL" ]]; then
    echo "  curl -sf ${FRONTEND_URL}/health" >&2
  fi
  if [[ -n "$FIRST_DOC_ID" ]]; then
    echo "  curl -sf ${API_URL}/preview/${FIRST_DOC_ID}" >&2
  fi
}

is_ci() { [[ "$SMOKE_MODE" == "ci" ]]; }

# Write a JSON result file.  Called on every stage outcome so the result
# is always available even when the script exits early.
write_result() {
  local stage="$1"
  local status="$2"
  local message="$3"

  STAGE_STATUS="${stage}:${status}"
  if [[ "$status" == "fail" ]]; then
    HAS_FAILURE=1
  fi

  local end_epoch
  end_epoch="$(date +%s)"
  local elapsed=$(( end_epoch - START_EPOCH ))

  mkdir -p "$(dirname "$RESULT_FILE")"
  python3 -c "
import json, os
path = '''${RESULT_FILE}'''
stage = '''${stage}'''
st = '''${status}'''
msg = '''${message}'''
ci_mode = '''${SMOKE_MODE}'''
api_url = '''${API_URL}'''
frontend_url = '''${FRONTEND_URL}'''
elapsed = ${elapsed}

result = {
    'smoke': 'document-flow',
    'status': st,
    'stage': stage,
    'message': msg,
    'elapsed_seconds': elapsed,
    'ci_mode': ci_mode,
    'api_url': api_url,
    'frontend_url': frontend_url,
    'timestamp': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
}
with open(path, 'w') as f:
    json.dump(result, f, indent=2)
print('Result written to ' + path)
" 2>/dev/null || log_info "Could not write result file (permissions or python error)"
}

run_stage() {
  local stage_name="$1"
  shift

  log_step "Stage: ${stage_name}"

  local exit_code=0
  "$@" || exit_code=$?

  if [[ $exit_code -eq 0 ]]; then
    log_ok "${stage_name}"
    write_result "$stage_name" "pass" ""
  else
    log_fail "${stage_name}"
    warn_logs
    write_result "$stage_name" "fail" "Stage failed with exit code ${exit_code}"
    if is_ci; then
      exit "$exit_code"
    fi
    # In local mode, continue to collect more failures
  fi
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 127
  fi
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local deadline=$(( SECONDS + TIMEOUT_SECONDS ))

  until curl -sfS --connect-timeout 5 -o /dev/null "$url" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${label} at ${url} after ${TIMEOUT_SECONDS}s." >&2
      return 1
    fi
    sleep "$POLL_SECONDS"
  done
  return 0
}

expect_health_json() {
  local url="$1"
  local expected_service="${2:-api}"
  local output
  output="$(curl -sfS "$url" 2>/dev/null)" || {
    echo "GET ${url} failed (curl exit $?)" >&2
    return 1
  }
  local status
  status="$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)" || {
    echo "Response from ${url} is not valid JSON" >&2
    echo "  Raw: ${output}" >&2
    return 1
  }
  if [[ "$status" != "ok" ]]; then
    echo "Expected status=ok at ${url}, got status=${status}" >&2
    echo "  Response: ${output}" >&2
    return 1
  fi
  return 0
}

# Health check that accepts the static frontend's plain-text "ok" body (served
# by nginx) as well as a JSON {"status":"ok"} body, for parity with the API.
expect_health_ok() {
  local url="$1"
  local output
  output="$(curl -sfS "$url" 2>/dev/null)" || {
    echo "GET ${url} failed (curl exit $?)" >&2
    return 1
  }
  local trimmed
  trimmed="$(echo "$output" | tr -d '[:space:]')"
  if [[ "$trimmed" == "ok" ]]; then
    return 0
  fi
  local status
  status="$(echo "$output" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)" || {
    echo "Response from ${url} is neither plain 'ok' nor valid health JSON" >&2
    echo "  Raw: ${output}" >&2
    return 1
  }
  if [[ "$status" != "ok" ]]; then
    echo "Expected health ok at ${url}, got: ${output}" >&2
    return 1
  fi
  return 0
}

# Authenticated JSON API call.  Writes the response body to stdout and sets
# the global CURL_JSON_HTTP_CODE to the HTTP status code.  Always returns 0
# so that bash `return` truncation (mod 256) cannot misclassify 5xx responses.
curl_json() {
  local method="$1"
  local url="$2"
  local body="${3:-}"
  local tmp_file
  tmp_file="$(mktemp)"
  local http_code

  if [[ -n "$body" ]]; then
    http_code="$(curl -sS -o "$tmp_file" -w '%{http_code}' -X "$method" \
      -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${AUTH_TOKEN}" \
      --data "$body" \
      "$url")"
  else
    http_code="$(curl -sS -o "$tmp_file" -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer ${AUTH_TOKEN}" \
      "$url")"
  fi

  CURL_JSON_HTTP_CODE="$http_code"
  echo "$http_code" > "$_HTTP_CODE_FILE"
  cat "$tmp_file"
  rm -f "$tmp_file"
}

json_get() {
  local expression="$1"
  python3 -c 'import json, sys; data=json.load(sys.stdin); value=eval(sys.argv[1], {}, {"data": data}); print("" if value is None else value)' "$expression"
}

# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

check_dependencies() {
  require_command curl
  require_command python3
  log_ok "curl and python3 available"
}

api_health() {
  log_info "Probing ${API_URL}/health"
  wait_for_url "API" "${API_URL}/health" || return 1
  expect_health_json "${API_URL}/health" "api" || return 1
  log_ok "API health returned status=ok"
}

frontend_health() {
  if [[ -z "$FRONTEND_URL" ]]; then
    log_skip "FRONTEND_URL not set — skipping frontend health check"
    write_result "frontend_health" "skip" "FRONTEND_URL not set"
    return 0
  fi
  log_info "Probing ${FRONTEND_URL}/health"
  wait_for_url "frontend" "${FRONTEND_URL}/health" || return 1
  expect_health_ok "${FRONTEND_URL}/health" || return 1
  log_ok "Frontend health returned status=ok"
}

mcp_health() {
  log_info "Probing MCP adapter at localhost:${MCP_HOST_PORT}"
  local deadline=$(( SECONDS + TIMEOUT_SECONDS ))
  # Use TCP check: /mcp returns 406 for plain GET (requires Accept headers), so
  # curl -f would always fail. Port reachability is sufficient as a health signal.
  until bash -c ":> /dev/tcp/127.0.0.1/${MCP_HOST_PORT}" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for MCP adapter on port ${MCP_HOST_PORT} after ${TIMEOUT_SECONDS}s." >&2
      return 1
    fi
    sleep "$POLL_SECONDS"
  done
  log_ok "MCP adapter is reachable on port ${MCP_HOST_PORT}"
}

auth_login() {
  if [[ -z "$SMOKE_ADMIN_EMAIL" || -z "$SMOKE_ADMIN_PASSWORD" ]]; then
    log_skip "SMOKE_ADMIN_EMAIL/PASSWORD not set — skipping auth login"
    write_result "auth_login" "skip" "SMOKE_ADMIN_EMAIL/PASSWORD not set"
    return 0
  fi

  local body
  body="$(python3 -c "import json; print(json.dumps({'email': '$SMOKE_ADMIN_EMAIL', 'password': '$SMOKE_ADMIN_PASSWORD'}))")"

  log_info "Logging in as ${SMOKE_ADMIN_EMAIL}"
  local response
  response="$(curl -sfS -X POST -H 'Content-Type: application/json' --data "$body" "${API_URL}/auth/login")" || {
    echo "POST /auth/login failed (HTTP error)" >&2
    return 1
  }

  AUTH_TOKEN="$(echo "$response" | json_get 'data["access_token"]')"
  if [[ -z "$AUTH_TOKEN" ]]; then
    echo "Login response did not contain access_token" >&2
    echo "  Response: ${response}" >&2
    return 1
  fi
  log_ok "Obtained access token (${#AUTH_TOKEN} chars)"
}

doc_bootstrap() {
  if ! command -v docker >/dev/null 2>&1; then
    log_skip "docker not found — skipping doc_bootstrap"
    write_result "doc_bootstrap" "skip" "docker not found"
    return 0
  fi

  if ! docker compose ps -q api >/dev/null 2>&1; then
    log_skip "api container not running — skipping doc_bootstrap"
    write_result "doc_bootstrap" "skip" "api container not running"
    return 0
  fi

  log_info "Running smoke bootstrap inside api container"
  local bootstrap_out
  bootstrap_out="$(docker compose exec -T \
    -e SMOKE_ADMIN_EMAIL="$SMOKE_ADMIN_EMAIL" \
    -e SMOKE_ADMIN_PASSWORD="$SMOKE_ADMIN_PASSWORD" \
    -e SMOKE_GROUP_NAME="$SMOKE_GROUP_NAME" \
    -e SMOKE_SOURCE_NAME="$SMOKE_SOURCE_NAME" \
    -e SMOKE_FIXTURE_DIR="$SMOKE_FIXTURE_DIR" \
    -e SMOKE_FIXTURE_NAME="$SMOKE_FIXTURE_NAME" \
    -e SMOKE_QUERY="$SMOKE_QUERY" \
    api python -m services.ops.smoke_bootstrap)" || {
    echo "Smoke bootstrap failed" >&2
    echo "  Output: ${bootstrap_out}" >&2
    return 1
  }

  SOURCE_ID="$(echo "$bootstrap_out" | python3 -c "
import json, sys
body = json.load(sys.stdin)
print(body.get('source_id', '') or '')
")"

  if [[ -z "$SOURCE_ID" ]]; then
    echo "Bootstrap did not return a source_id" >&2
    echo "  Output: ${bootstrap_out}" >&2
    return 1
  fi

  log_ok "Bootstrap created source_id=${SOURCE_ID}"
}

doc_ingest() {
  if [[ -z "$AUTH_TOKEN" ]]; then
    log_skip "Not authenticated — skipping doc_ingest"
    write_result "doc_ingest" "skip" "AUTH_TOKEN not set"
    return 0
  fi
  if [[ -z "$SOURCE_ID" ]]; then
    log_skip "No source ID — skipping doc_ingest"
    write_result "doc_ingest" "skip" "SOURCE_ID not set"
    return 0
  fi

  log_info "Triggering sync for source ${SOURCE_ID}"
  local response http_code tmp_resp
  tmp_resp="$(mktemp)"
  # Call curl directly so the http_code is captured in this shell, not a subshell
  # (curl_json sets CURL_JSON_HTTP_CODE inside $() which is a subshell and the
  # assignment does not propagate back to the caller).
  http_code="$(curl -sS -o "$tmp_resp" -w '%{http_code}' -X POST \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    "${API_URL}/admin/ingestion/${SOURCE_ID}/sync-now")"
  response="$(cat "$tmp_resp")"
  rm -f "$tmp_resp"

  if (( http_code < 200 || http_code >= 300 )); then
    echo "Sync returned HTTP ${http_code}" >&2
    echo "  Response: ${response}" >&2
    return 1
  fi

  local indexed skipped failed_count
  indexed="$(echo "$response" | json_get 'data.get("created", 0)')"
  skipped="$(echo "$response" | json_get 'data.get("skipped", 0)')"
  failed_count="$(echo "$response" | json_get 'data.get("failed_discovery", 0) + data.get("failed_enqueue", 0)')"

  if [[ "$failed_count" != "0" ]]; then
    echo "Ingestion reported failed=${failed_count}" >&2
    return 1
  fi
  if [[ "$indexed" == "0" && "$skipped" == "0" ]]; then
    echo "Ingestion did not index or skip any documents" >&2
    return 1
  fi

  log_info "Sync result: indexed=${indexed}, skipped=${skipped}, failed=${failed_count}"

  if [[ "$indexed" == "1" ]]; then
    log_info "Waiting up to ${TIMEOUT_SECONDS}s for indexing to complete"
    sleep "$POLL_SECONDS"
  fi

  log_ok "Ingestion sync completed"
}

doc_search() {
  if [[ -z "$AUTH_TOKEN" ]]; then
    log_skip "Not authenticated — skipping doc_search"
    write_result "doc_search" "skip" "AUTH_TOKEN not set"
    return 0
  fi

  local body
  body="$(python3 -c "import json; print(json.dumps({'query': '${SMOKE_QUERY}', 'page': 1, 'page_size': 5}))")"

  log_info "Searching for '${SMOKE_QUERY}'"
  local response
  response="$(curl_json POST "${API_URL}/search" "$body")"
  local http_code
  http_code="$(cat "$_HTTP_CODE_FILE" 2>/dev/null || echo 0)"

  if (( http_code < 200 || http_code >= 300 )); then
    echo "Search returned HTTP ${http_code}" >&2
    echo "  Response: ${response}" >&2
    return 1
  fi

  local total
  total="$(echo "$response" | json_get 'data.get("total", 0)')"
  log_info "Search returned total=${total:-0} results"

  FIRST_DOC_ID="$(echo "$response" | python3 -c "
import json, sys
body = json.load(sys.stdin)
results = body.get('results', [])
if results:
    print(results[0].get('document_id', '') or '')
")"
  if [[ -n "$FIRST_DOC_ID" ]]; then
    log_info "Captured document_id=${FIRST_DOC_ID} for preview/download"
  fi

  log_ok "Search endpoint is accessible and returns valid JSON"
}

doc_preview() {
  if [[ -z "$FIRST_DOC_ID" ]]; then
    log_skip "No document ID available — skipping doc_preview"
    write_result "doc_preview" "skip" "No document ID available"
    return 0
  fi

  log_info "Fetching preview for ${FIRST_DOC_ID}"
  local response
  response="$(curl_json GET "${API_URL}/preview/${FIRST_DOC_ID}")"
  local http_code
  http_code="$(cat "$_HTTP_CODE_FILE" 2>/dev/null || echo 0)"

  if (( http_code < 200 || http_code >= 300 )); then
    echo "Preview returned HTTP ${http_code}" >&2
    echo "  Response: ${response}" >&2
    return 1
  fi

  local snippet
  snippet="$(echo "$response" | json_get 'data.get("snippet", "")')"
  if [[ -z "$snippet" ]]; then
    echo "Preview response missing snippet field" >&2
    echo "  Response: ${response}" >&2
    return 1
  fi

  log_info "Preview snippet (${#snippet} chars) retrieved successfully"
  log_ok "Preview endpoint returns valid JSON with snippet"
}

doc_text() {
  if [[ -z "$FIRST_DOC_ID" ]]; then
    log_skip "No document ID available — skipping doc_text"
    write_result "doc_text" "skip" "No document ID available"
    return 0
  fi

  log_info "Fetching full text for ${FIRST_DOC_ID}"
  local response
  response="$(curl_json GET "${API_URL}/documents/${FIRST_DOC_ID}/text")"
  local http_code
  http_code="$(cat "$_HTTP_CODE_FILE" 2>/dev/null || echo 0)"

  if (( http_code < 200 || http_code >= 300 )); then
    echo "Document text returned HTTP ${http_code}" >&2
    echo "  Response: ${response}" >&2
    return 1
  fi

  local text_len
  text_len="$(echo "$response" | json_get 'len(data.get("text", ""))')"
  log_info "Document text length: ${text_len:-0} chars"
  log_ok "Document text endpoint returns valid JSON"
}

doc_download() {
  if [[ -z "$FIRST_DOC_ID" ]]; then
    log_skip "No document ID available — skipping doc_download"
    write_result "doc_download" "skip" "No document ID available"
    return 0
  fi

  log_info "Downloading document ${FIRST_DOC_ID}"
  local tmp_file
  tmp_file="$(mktemp)"
  local http_code
  http_code="$(curl -sS -o "$tmp_file" -w '%{http_code}' \
    -H "Authorization: Bearer ${AUTH_TOKEN}" \
    "${API_URL}/download/${FIRST_DOC_ID}")"

  if (( http_code < 200 || http_code >= 300 )); then
    echo "Download returned HTTP ${http_code}" >&2
    rm -f "$tmp_file"
    return 1
  fi

  local size
  size="$(stat --format=%s "$tmp_file" 2>/dev/null || echo 0)"
  rm -f "$tmp_file"

  if (( size == 0 )); then
    echo "Download returned empty file (HTTP ${http_code})" >&2
    return 1
  fi

  log_info "Downloaded ${size} bytes"
  log_ok "Download endpoint returns file content"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
log_step "Starting document-flow smoke test (mode=${SMOKE_MODE})"
log_info "API: ${API_URL}"
if [[ -n "$FRONTEND_URL" ]]; then
  log_info "Frontend: ${FRONTEND_URL}"
else
  log_info "Frontend: not configured (set FRONTEND_URL to check)"
fi
log_info "Result file: ${RESULT_FILE}"

# Stage 1 — dependencies
run_stage "check_dependencies" check_dependencies

# Stage 2 — API health
run_stage "api_health" api_health

# Stage 3 — frontend health (skip if unset, fail if unreachable)
if [[ -n "$FRONTEND_URL" ]]; then
  run_stage "frontend_health" frontend_health
else
  log_skip "Frontend health check skipped (FRONTEND_URL not set)"
  write_result "frontend_health" "skip" "FRONTEND_URL not set"
fi

# Stage 3b — MCP adapter health
MCP_HOST_PORT="${MCP_HOST_PORT:-8001}"
run_stage "mcp_health" mcp_health

# Stage 4 — document bootstrap via Docker (skip if Docker absent)
run_stage "doc_bootstrap" doc_bootstrap

# Stage 5 — auth login (skip if creds unset)
run_stage "auth_login" auth_login

# Stage 6 — document ingestion + poll (skip if no source or token)
run_stage "doc_ingest" doc_ingest

# Stage 7 — document search (extracts FIRST_DOC_ID)
run_stage "doc_search" doc_search

# If SMOKE_DOCUMENT_ID is set, it overrides whatever search found
if [[ -n "$SMOKE_DOCUMENT_ID" ]]; then
  FIRST_DOC_ID="$SMOKE_DOCUMENT_ID"
  log_info "Overriding document ID with SMOKE_DOCUMENT_ID=${FIRST_DOC_ID}"
fi

# Stage 8 — document preview (skip if no doc available)
run_stage "doc_preview" doc_preview

# Stage 9 — document text (skip if no doc available)
run_stage "doc_text" doc_text

# Stage 10 — document download (skip if no doc available)
run_stage "doc_download" doc_download

# Final result
END_EPOCH="$(date +%s)"
TOTAL_ELAPSED=$(( END_EPOCH - START_EPOCH ))

if [[ $HAS_FAILURE -eq 1 ]]; then
  write_result "final" "fail" "One or more stages failed"
  echo ""
  log_fail "Document-flow smoke test FAILED after ${TOTAL_ELAPSED}s"
  is_ci && exit 1
  exit 1
fi

write_result "final" "pass" "All stages passed"
echo ""
log_step "Document-flow smoke test PASSED (${TOTAL_ELAPSED}s)"
exit 0
