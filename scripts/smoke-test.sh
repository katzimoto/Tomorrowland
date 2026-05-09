#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/smoke-test.sh [--use-running] [--keep-running]

Runs a no-mock smoke test against the production Docker Compose stack.

Options:
  --use-running   Do not start Compose; test the stack that is already running.
  --keep-running  Leave containers and volumes in place after the test.
  -h, --help      Show this help text.

Environment overrides:
  API_URL                 Default: http://localhost:${API_PORT:-8000}
  FRONTEND_URL            Default: http://localhost:${FRONTEND_PORT:-8080}
  SMOKE_ADMIN_EMAIL       Default: smoke-admin@example.com
  SMOKE_ADMIN_PASSWORD    Default: neverland-smoke-password
  SMOKE_GROUP_NAME        Default: smoke-operators
  SMOKE_SOURCE_NAME       Default: smoke-folder-source
  SMOKE_FIXTURE_DIR       Default: /data/smoke-fixtures
  SMOKE_FIXTURE_NAME      Default: neverland-smoke-document.txt
  SMOKE_TIMEOUT_SECONDS   Default: 300
  SMOKE_POLL_SECONDS      Default: 5
USAGE
}

USE_RUNNING=0
KEEP_RUNNING=0
for arg in "$@"; do
  case "$arg" in
    --use-running)
      USE_RUNNING=1
      ;;
    --keep-running)
      KEEP_RUNNING=1
      ;;
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

API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-8080}"
API_URL="${API_URL:-http://localhost:${API_PORT}}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:${FRONTEND_PORT}}"
SMOKE_ADMIN_EMAIL="${SMOKE_ADMIN_EMAIL:-smoke-admin@example.com}"
SMOKE_ADMIN_PASSWORD="${SMOKE_ADMIN_PASSWORD:-neverland-smoke-password}"
SMOKE_GROUP_NAME="${SMOKE_GROUP_NAME:-smoke-operators}"
SMOKE_SOURCE_NAME="${SMOKE_SOURCE_NAME:-smoke-folder-source}"
SMOKE_FIXTURE_DIR="${SMOKE_FIXTURE_DIR:-/data/smoke-fixtures}"
SMOKE_FIXTURE_NAME="${SMOKE_FIXTURE_NAME:-neverland-smoke-document.txt}"
SMOKE_TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-300}"
SMOKE_POLL_SECONDS="${SMOKE_POLL_SECONDS:-5}"
SMOKE_QUERY="${SMOKE_QUERY:-neverland-smoke-unique-token}"
SMOKE_FIXTURE_PATH="${SMOKE_FIXTURE_DIR%/}/${SMOKE_FIXTURE_NAME}"

TMP_DIR="$(mktemp -d)"
STARTED_STACK=0
cleanup() {
  local exit_code=$?
  rm -rf "$TMP_DIR"

  if [[ $exit_code -ne 0 ]]; then
    echo "Smoke test failed. Inspect service logs with:" >&2
    echo "  docker compose logs --tail=200 api frontend migrate postgres elasticsearch qdrant" >&2
  fi

  if [[ $STARTED_STACK -eq 1 && $KEEP_RUNNING -eq 0 ]]; then
    echo "Tearing down Compose stack and volumes."
    docker compose down -v
  elif [[ $STARTED_STACK -eq 1 && $KEEP_RUNNING -eq 1 ]]; then
    echo "Leaving Compose stack running for debugging (--keep-running)."
  fi

  return $exit_code
}
trap cleanup EXIT

log_step() {
  echo "==> $*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 127
  fi
}

json_get() {
  local expression="$1"
  python -c 'import json, sys; data=json.load(sys.stdin); value=eval(sys.argv[1], {}, {"data": data}); print("" if value is None else value)' "$expression"
}

curl_json() {
  local method="$1"
  local url="$2"
  local body="${3:-}"
  local output="$TMP_DIR/response.json"
  local status

  if [[ -n "$body" ]]; then
    status="$(curl -sS -o "$output" -w '%{http_code}' -X "$method" \
      -H 'Content-Type: application/json' \
      -H "Authorization: Bearer ${AUTH_TOKEN}" \
      --data "$body" \
      "$url")"
  else
    status="$(curl -sS -o "$output" -w '%{http_code}' -X "$method" \
      -H "Authorization: Bearer ${AUTH_TOKEN}" \
      "$url")"
  fi

  if [[ "$status" != 2* ]]; then
    echo "Request failed: $method $url returned HTTP $status" >&2
    cat "$output" >&2 || true
    exit 1
  fi

  cat "$output"
}

wait_for_url() {
  local label="$1"
  local url="$2"
  local deadline=$((SECONDS + SMOKE_TIMEOUT_SECONDS))

  until curl -fsS "$url" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${label} at ${url} after ${SMOKE_TIMEOUT_SECONDS}s." >&2
      exit 1
    fi
    sleep "$SMOKE_POLL_SECONDS"
  done
}

wait_for_search_result() {
  local deadline=$((SECONDS + SMOKE_TIMEOUT_SECONDS))
  local body doc_id
  body="$(SMOKE_QUERY="$SMOKE_QUERY" python -c 'import json, os; print(json.dumps({"query": os.environ["SMOKE_QUERY"], "page": 1, "page_size": 10}))')"

  while true; do
    doc_id="$(curl_json POST "${API_URL}/search" "$body" | python -c 'import json, sys; fixture_name=sys.argv[1]; query=sys.argv[2]; data=json.load(sys.stdin); print(next((result["doc_id"] for result in data.get("results", []) if result.get("title") == fixture_name or query in (result.get("chunk_text") or "")), ""))' "$SMOKE_FIXTURE_NAME" "$SMOKE_QUERY")"
    if [[ -n "$doc_id" ]]; then
      echo "$doc_id"
      return 0
    fi
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for fixture document to appear in search." >&2
      exit 1
    fi
    sleep "$SMOKE_POLL_SECONDS"
  done
}

require_command docker
require_command curl
require_command python

if [[ $USE_RUNNING -eq 0 ]]; then
  log_step "Starting production Compose stack"
  docker compose up --build -d
  STARTED_STACK=1
else
  log_step "Using already running Compose stack"
fi

log_step "Waiting for API health"
wait_for_url "API" "${API_URL}/health"

log_step "Seeding smoke admin and group inside the API container"
docker compose exec -T \
  -e SMOKE_ADMIN_EMAIL="$SMOKE_ADMIN_EMAIL" \
  -e SMOKE_ADMIN_PASSWORD="$SMOKE_ADMIN_PASSWORD" \
  -e SMOKE_GROUP_NAME="$SMOKE_GROUP_NAME" \
  api python - <<'PY'
from __future__ import annotations

import os

import sqlalchemy as sa

from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings
from shared.db import db_uuid

settings = Settings()
engine = sa.create_engine(settings.postgres_url)
email = os.environ["SMOKE_ADMIN_EMAIL"]
password = os.environ["SMOKE_ADMIN_PASSWORD"]
group_name = os.environ["SMOKE_GROUP_NAME"]

with engine.begin() as connection:
    repo = AuthRepository(connection)
    repo.ensure_group(group_name)
    existing = repo.get_user_by_email(email)
    if existing is None:
        repo.create_local_user(
            email=email,
            password_hash=hash_password(password),
            display_name="Smoke Admin",
            is_admin=True,
            group_names=[group_name],
        )
    else:
        connection.execute(
            sa.text(
                """
                UPDATE users
                SET display_name = :display_name,
                    auth_source = 'local',
                    password_hash = :password_hash,
                    is_admin = true
                WHERE id = :id
                """
            ),
            {
                "display_name": "Smoke Admin",
                "password_hash": hash_password(password),
                "id": db_uuid(existing.id),
            },
        )
        repo.set_user_groups(existing.id, [group_name])
PY

log_step "Writing deterministic fixture document in the Compose files volume"
docker compose exec -T \
  -e SMOKE_FIXTURE_DIR="$SMOKE_FIXTURE_DIR" \
  -e SMOKE_FIXTURE_PATH="$SMOKE_FIXTURE_PATH" \
  -e SMOKE_QUERY="$SMOKE_QUERY" \
  api sh -c 'mkdir -p "$SMOKE_FIXTURE_DIR" && cat > "$SMOKE_FIXTURE_PATH"' <<EOF_FIXTURE
Neverland smoke fixture.
This deterministic document verifies ingestion, search, preview, and download.
Unique query token: ${SMOKE_QUERY}.
EOF_FIXTURE

log_step "Logging in as smoke admin"
LOGIN_BODY="$(SMOKE_ADMIN_EMAIL="$SMOKE_ADMIN_EMAIL" SMOKE_ADMIN_PASSWORD="$SMOKE_ADMIN_PASSWORD" python -c 'import json, os; print(json.dumps({"email": os.environ["SMOKE_ADMIN_EMAIL"], "password": os.environ["SMOKE_ADMIN_PASSWORD"]}))')"
AUTH_TOKEN="$(curl -fsS -X POST -H 'Content-Type: application/json' --data "$LOGIN_BODY" "${API_URL}/auth/login" | json_get 'data["access_token"]')"
if [[ -z "$AUTH_TOKEN" ]]; then
  echo "Login succeeded but no access token was returned." >&2
  exit 1
fi

log_step "Creating or reusing smoke group"
GROUP_ID="$(curl_json GET "${API_URL}/admin/groups" | python -c 'import json, sys; name=sys.argv[1]; data=json.load(sys.stdin); print(next((group["id"] for group in data if group.get("name") == name), ""))' "$SMOKE_GROUP_NAME")"
if [[ -z "$GROUP_ID" ]]; then
  GROUP_BODY="$(SMOKE_GROUP_NAME="$SMOKE_GROUP_NAME" python -c 'import json, os; print(json.dumps({"name": os.environ["SMOKE_GROUP_NAME"]}))')"
  GROUP_ID="$(curl_json POST "${API_URL}/admin/groups" "$GROUP_BODY" | json_get 'data["id"]')"
fi

log_step "Creating or reusing smoke folder source"
SOURCE_ID="$(curl_json GET "${API_URL}/admin/sources" | python -c 'import json, sys; name=sys.argv[1]; data=json.load(sys.stdin); print(next((source["id"] for source in data if source.get("name") == name), ""))' "$SMOKE_SOURCE_NAME")"
if [[ -z "$SOURCE_ID" ]]; then
  SOURCE_BODY="$(SMOKE_SOURCE_NAME="$SMOKE_SOURCE_NAME" SMOKE_FIXTURE_DIR="$SMOKE_FIXTURE_DIR" python -c 'import json, os; print(json.dumps({"name": os.environ["SMOKE_SOURCE_NAME"], "type": "folder", "path": os.environ["SMOKE_FIXTURE_DIR"], "source_language": "en", "enabled": True, "config": {}}))')"
  SOURCE_ID="$(curl_json POST "${API_URL}/admin/sources" "$SOURCE_BODY" | json_get 'data["id"]')"
fi

log_step "Granting smoke group access to the source"
GRANT_BODY="$(GROUP_ID="$GROUP_ID" python -c 'import json, os; print(json.dumps({"group_id": os.environ["GROUP_ID"]}))')"
GRANT_STATUS="$(curl -sS -o "$TMP_DIR/grant.json" -w '%{http_code}' -X POST \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer ${AUTH_TOKEN}" \
  --data "$GRANT_BODY" \
  "${API_URL}/admin/sources/${SOURCE_ID}/permissions")"
if [[ "$GRANT_STATUS" != 2* ]]; then
  echo "Permission grant returned HTTP ${GRANT_STATUS}; continuing because an existing grant may already be present." >&2
fi

log_step "Triggering synchronous ingestion"
INGEST_RESULT="$(curl_json POST "${API_URL}/admin/ingestion/${SOURCE_ID}/sync-now")"
INDEXED="$(printf '%s' "$INGEST_RESULT" | json_get 'data.get("indexed", 0)')"
SKIPPED="$(printf '%s' "$INGEST_RESULT" | json_get 'data.get("skipped", 0)')"
FAILED_COUNT="$(printf '%s' "$INGEST_RESULT" | json_get 'data.get("failed", 0)')"
if [[ "$FAILED_COUNT" != "0" ]]; then
  echo "Ingestion reported failed=${FAILED_COUNT}." >&2
  exit 1
fi
if [[ "$INDEXED" == "0" && "$SKIPPED" == "0" ]]; then
  echo "Ingestion did not index or skip any documents." >&2
  exit 1
fi

log_step "Polling search for fixture document"
DOC_ID="$(wait_for_search_result)"
if [[ -z "$DOC_ID" ]]; then
  echo "Search did not return a document ID." >&2
  exit 1
fi

log_step "Fetching preview content"
PREVIEW_SNIPPET="$(curl_json GET "${API_URL}/preview/${DOC_ID}" | json_get 'data.get("snippet", "")')"
if [[ "$PREVIEW_SNIPPET" != *"$SMOKE_QUERY"* ]]; then
  echo "Preview snippet did not include the smoke query token." >&2
  exit 1
fi

log_step "Downloading fixture document"
DOWNLOAD_FILE="$TMP_DIR/downloaded-fixture.txt"
curl -fsS -H "Authorization: Bearer ${AUTH_TOKEN}" "${API_URL}/download/${DOC_ID}" -o "$DOWNLOAD_FILE"
if [[ ! -s "$DOWNLOAD_FILE" ]]; then
  echo "Downloaded fixture is empty." >&2
  exit 1
fi

log_step "Checking frontend reachability"
wait_for_url "frontend" "${FRONTEND_URL}/"
wait_for_url "frontend health" "${FRONTEND_URL}/health"

log_step "Smoke test completed successfully"
exit 0
