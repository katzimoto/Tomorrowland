#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="setup-env"
VERSION="1.0"

log() { printf '[%s] %s\n' "$SCRIPT_NAME" "$*"; }
warn() { printf '[%s] WARNING: %s\n' "$SCRIPT_NAME" "$*" >&2; }
fail() { printf '[%s] ERROR: %s\n' "$SCRIPT_NAME" "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
Usage: scripts/setup-env.sh [OPTIONS]

Generate a Tomorrowland Compose environment file interactively or with safe
defaults. Never overwrites an existing file without --force.

Options:
  --output FILE       Output path (default: .env)
  --airgap            Generate air-gapped deployment template
  --defaults          Non-interactive: use safe defaults + generated secrets
  --force             Overwrite existing output file
  --print             Print to stdout instead of writing to file
  -h, --help          Show this help

Examples:
  scripts/setup-env.sh --output .env
  scripts/setup-env.sh --defaults --output .env
  scripts/setup-env.sh --airgap --defaults --output .env.airgap
  scripts/setup-env.sh --defaults --print
USAGE
}

# Defaults
OUTPUT=""
AIRGAP=0
DEFAULTS=0
FORCE=0
PRINT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT="${2:-}"; shift 2 ;;
    --airgap)
      AIRGAP=1; shift ;;
    --defaults)
      DEFAULTS=1; shift ;;
    --force)
      FORCE=1; shift ;;
    --print)
      PRINT=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      fail "unknown argument: $1" ;;
  esac
done

# Resolve default output name
if [[ -z "$OUTPUT" ]]; then
  if [[ "$AIRGAP" -eq 1 ]]; then
    OUTPUT=".env.airgap"
  else
    OUTPUT=".env"
  fi
fi

# --- helpers ---

secure_rand() {
  local len="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 "$len" | tr -dc 'A-Za-z0-9' | head -c "$len"
  else
    # fallback using /dev/urandom
    head -c "$((len * 2))" /dev/urandom | tr -dc 'A-Za-z0-9' | head -c "$len"
  fi
}

prompt() {
  local key="$1"
  local default="$2"
  local value=""
  if [[ "$DEFAULTS" -eq 1 ]]; then
    printf '%s\n' "$default"
    return
  fi
  read -rp "$key [$default]: " value
  printf '%s\n' "${value:-$default}"
}

prompt_secret() {
  local key="$1"
  local default="$2"
  local value=""
  if [[ "$DEFAULTS" -eq 1 ]]; then
    printf '%s\n' "$default"
    return
  fi
  read -rsp "$key [press Enter to generate]: " value
  printf '\n'
  if [[ -z "$value" ]]; then
    printf '%s\n' "$default"
  else
    printf '%s\n' "$value"
  fi
}

prompt_yesno() {
  local key="$1"
  local default="$2"
  local value=""
  if [[ "$DEFAULTS" -eq 1 ]]; then
    printf '%s\n' "$default"
    return
  fi
  read -rp "$key (true/false) [$default]: " value
  value="${value:-$default}"
  if [[ "$value" != "true" && "$value" != "false" ]]; then
    warn "invalid boolean '$value', using default $default"
    value="$default"
  fi
  printf '%s\n' "$value"
}

validate_port() {
  local val="$1"
  local key="$2"
  if [[ "$val" =~ ^[0-9]+$ ]] && [[ "$val" -ge 1 && "$val" -le 65535 ]]; then
    printf '%s\n' "$val"
  else
    warn "invalid port for $key: $val; using default"
    printf '%s\n' "$3"
  fi
}

# --- safety checks ---

if [[ "$PRINT" -eq 0 ]]; then
  if [[ -e "$OUTPUT" && "$FORCE" -eq 0 ]]; then
    fail "output file already exists: $OUTPUT. Use --force to overwrite."
  fi
fi

# --- generate values ---

APP_ENV="$(prompt "APP_ENV" "prod")"
APP_VERSION="$(prompt "APP_VERSION" "0.1.0")"
BUILD_COMMIT="$(prompt "BUILD_COMMIT" "unknown")"
LOG_LEVEL="$(prompt "LOG_LEVEL" "info")"

# Secrets
POSTGRES_PASSWORD="$(prompt_secret "POSTGRES_PASSWORD" "$(secure_rand 32)")"
JWT_SECRET="$(prompt_secret "JWT_SECRET" "$(secure_rand 48)")"

# Auth
AUTH_PROVIDER="$(prompt "AUTH_PROVIDER (local/ldap/both)" "local")"
LDAP_URL=""
LDAP_BASE_DN=""
LDAP_BIND_USER=""
LDAP_BIND_PASSWORD=""
if [[ "$AUTH_PROVIDER" == "ldap" || "$AUTH_PROVIDER" == "both" ]]; then
  LDAP_URL="$(prompt "LDAP_URL" "ldap://domain-controller:389")"
  LDAP_BASE_DN="$(prompt "LDAP_BASE_DN" "DC=company,DC=local")"
  LDAP_BIND_USER="$(prompt "LDAP_BIND_USER" "cn=svc-search,DC=company,DC=local")"
  LDAP_BIND_PASSWORD="$(prompt_secret "LDAP_BIND_PASSWORD" "$(secure_rand 24)")"
fi

# Ports
API_PORT="$(validate_port "$(prompt "API_PORT" "8000")" "API_PORT" "8000")"
FRONTEND_PORT="$(validate_port "$(prompt "FRONTEND_PORT" "8080")" "FRONTEND_PORT" "8080")"
POSTGRES_PORT="$(validate_port "$(prompt "POSTGRES_PORT" "5432")" "POSTGRES_PORT" "5432")"
KAFKA_PORT="$(validate_port "$(prompt "KAFKA_PORT" "9092")" "KAFKA_PORT" "9092")"
ELASTICSEARCH_PORT="$(validate_port "$(prompt "ELASTICSEARCH_PORT" "9200")" "ELASTICSEARCH_PORT" "9200")"
QDRANT_PORT="$(validate_port "$(prompt "QDRANT_PORT" "6333")" "QDRANT_PORT" "6333")"
LIBRETRANSLATE_PORT="$(validate_port "$(prompt "LIBRETRANSLATE_PORT" "5000")" "LIBRETRANSLATE_PORT" "5000")"
OLLAMA_PORT="$(validate_port "$(prompt "OLLAMA_PORT" "11434")" "OLLAMA_PORT" "11434")"

# Core service URLs
POSTGRES_DB="$(prompt "POSTGRES_DB" "app")"
POSTGRES_USER="$(prompt "POSTGRES_USER" "postgres")"
POSTGRES_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"
KAFKA_BROKER="$(prompt "KAFKA_BROKER" "kafka:9092")"
ELASTIC_URL="$(prompt "ELASTIC_URL" "http://elasticsearch:9200")"
QDRANT_URL="$(prompt "QDRANT_URL" "http://qdrant:6333")"
FILES_ROOT="$(prompt "FILES_ROOT" "/data")"
CORS_ORIGINS="$(prompt "CORS_ORIGINS" "http://localhost:8080")"
LIBRETRANSLATE_URL="$(prompt "LIBRETRANSLATE_URL" "http://libretranslate:5000")"
OLLAMA_URL="$(prompt "OLLAMA_URL" "http://ollama:11434")"
OLLAMA_MODEL="$(prompt "OLLAMA_MODEL" "mistral")"

# Translation
SUPPORTED_TRANSLATION_SOURCE_LANGUAGES="$(prompt "SUPPORTED_TRANSLATION_SOURCE_LANGUAGES" "en,he,zh,ko,th,ar,fr,ru,es")"
SUPPORTED_TRANSLATION_TARGET_LANGUAGES="$(prompt "SUPPORTED_TRANSLATION_TARGET_LANGUAGES" "en,he,zh,ko,th,ar,fr,ru,es")"

# Embedding
EMBEDDING_PROVIDER="$(prompt "EMBEDDING_PROVIDER (ollama/deterministic-test/empty)" "")"
EMBEDDING_MODEL="$(prompt "EMBEDDING_MODEL" "nomic-embed-text")"
EMBEDDING_URL="$(prompt "EMBEDDING_URL" "")"
EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD="$(prompt_yesno "EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD" "false")"

# Feature flags
FEATURE_DOCUMENT_COMMENTS="$(prompt_yesno "FEATURE_DOCUMENT_COMMENTS" "true")"
FEATURE_RAG_QA="$(prompt_yesno "FEATURE_RAG_QA" "true")"
FEATURE_SUMMARIZATION="$(prompt_yesno "FEATURE_SUMMARIZATION" "true")"
FEATURE_ENTITY_EXTRACTION="$(prompt_yesno "FEATURE_ENTITY_EXTRACTION" "true")"
FEATURE_ANNOTATIONS="$(prompt_yesno "FEATURE_ANNOTATIONS" "true")"
FEATURE_SUBSCRIPTIONS="$(prompt_yesno "FEATURE_SUBSCRIPTIONS" "true")"
FEATURE_EXPERTISE_MAP="$(prompt_yesno "FEATURE_EXPERTISE_MAP" "true")"
FEATURE_RELATED_DOCS="$(prompt_yesno "FEATURE_RELATED_DOCS" "true")"
FEATURE_AUTO_TAGGING="$(prompt_yesno "FEATURE_AUTO_TAGGING" "true")"
AUTO_ENRICH_THRESHOLD="$(prompt "AUTO_ENRICH_THRESHOLD" "5")"
INGEST_MODE="$(prompt "INGEST_MODE (hybrid/watch/poll)" "hybrid")"

# Persistent volume names (from #222)
FILES_VOLUME="$(prompt "TOMORROWLAND_FILES_VOLUME" "tomorrowland_files_data")"
POSTGRES_VOLUME="$(prompt "TOMORROWLAND_POSTGRES_VOLUME" "tomorrowland_postgres_data")"
KAFKA_VOLUME="$(prompt "TOMORROWLAND_KAFKA_VOLUME" "tomorrowland_kafka_data")"
ELASTICSEARCH_VOLUME="$(prompt "TOMORROWLAND_ELASTICSEARCH_VOLUME" "tomorrowland_elasticsearch_data")"
QDRANT_VOLUME="$(prompt "TOMORROWLAND_QDRANT_VOLUME" "tomorrowland_qdrant_data")"
LIBRETRANSLATE_VOLUME="$(prompt "TOMORROWLAND_LIBRETRANSLATE_VOLUME" "tomorrowland_libretranslate_data")"
OLLAMA_VOLUME="$(prompt "TOMORROWLAND_OLLAMA_VOLUME" "tomorrowland_ollama_data")"
PROMETHEUS_VOLUME="$(prompt "TOMORROWLAND_PROMETHEUS_VOLUME" "tomorrowland_prometheus_data")"
GRAFANA_VOLUME="$(prompt "TOMORROWLAND_GRAFANA_VOLUME" "tomorrowland_grafana_data")"

# Folder source paths (airgap-relevant)
FOLDER_SOURCE_HOST_PATH=""
FOLDER_SOURCE_CONTAINER_PATH=""
if [[ "$AIRGAP" -eq 1 ]]; then
  FOLDER_SOURCE_HOST_PATH="$(prompt "TOMORROWLAND_FOLDER_SOURCE_HOST_PATH" "./operator-data/folder-source")"
  FOLDER_SOURCE_CONTAINER_PATH="$(prompt "TOMORROWLAND_FOLDER_SOURCE_CONTAINER_PATH" "/sources/folder")"
fi

# Airgap image tags
BACKEND_IMAGE=""
FRONTEND_IMAGE=""
LIBRETRANSLATE_IMAGE=""
if [[ "$AIRGAP" -eq 1 ]]; then
  BACKEND_IMAGE="$(prompt "TOMORROWLAND_BACKEND_IMAGE" "tomorrowland/backend:airgap")"
  FRONTEND_IMAGE="$(prompt "TOMORROWLAND_FRONTEND_IMAGE" "tomorrowland/frontend:airgap")"
  LIBRETRANSLATE_IMAGE="$(prompt "TOMORROWLAND_LIBRETRANSLATE_IMAGE" "tomorrowland/libretranslate:airgap")"
fi

# --- build output ---

out=""

out+="# Tomorrowland environment configuration\n"
out+="# Generated by scripts/setup-env.sh v${VERSION}\n"
out+="# $(date -u +%Y-%m-%dT%H:%M:%SZ)\n"
out+="\n"

out+="# Core deployment\n"
out+="APP_ENV=${APP_ENV}\n"
out+="APP_VERSION=${APP_VERSION}\n"
out+="BUILD_COMMIT=${BUILD_COMMIT}\n"
out+="LOG_LEVEL=${LOG_LEVEL}\n"
out+="\n"

out+="# Database\n"
out+="POSTGRES_DB=${POSTGRES_DB}\n"
out+="POSTGRES_USER=${POSTGRES_USER}\n"
out+="POSTGRES_PASSWORD=${POSTGRES_PASSWORD}\n"
out+="POSTGRES_URL=${POSTGRES_URL}\n"
out+="\n"

out+="# Messaging and search\n"
out+="KAFKA_BROKER=${KAFKA_BROKER}\n"
out+="ELASTIC_URL=${ELASTIC_URL}\n"
out+="QDRANT_URL=${QDRANT_URL}\n"
out+="\n"

out+="# File storage\n"
out+="FILES_ROOT=${FILES_ROOT}\n"
out+="\n"

out+="# Security\n"
out+="JWT_SECRET=${JWT_SECRET}\n"
out+="CORS_ORIGINS=${CORS_ORIGINS}\n"
out+="\n"

out+="# Translation\n"
out+="LIBRETRANSLATE_URL=${LIBRETRANSLATE_URL}\n"
out+="SUPPORTED_TRANSLATION_SOURCE_LANGUAGES=${SUPPORTED_TRANSLATION_SOURCE_LANGUAGES}\n"
out+="SUPPORTED_TRANSLATION_TARGET_LANGUAGES=${SUPPORTED_TRANSLATION_TARGET_LANGUAGES}\n"
out+="\n"

out+="# Local LLM\n"
out+="OLLAMA_URL=${OLLAMA_URL}\n"
out+="OLLAMA_MODEL=${OLLAMA_MODEL}\n"
out+="\n"

out+="# Auth\n"
out+="AUTH_PROVIDER=${AUTH_PROVIDER}\n"
if [[ "$AUTH_PROVIDER" == "ldap" || "$AUTH_PROVIDER" == "both" ]]; then
  out+="LDAP_URL=${LDAP_URL}\n"
  out+="LDAP_BASE_DN=${LDAP_BASE_DN}\n"
  out+="LDAP_BIND_USER=${LDAP_BIND_USER}\n"
  out+="LDAP_BIND_PASSWORD=${LDAP_BIND_PASSWORD}\n"
fi
out+="\n"

out+="# Feature flags\n"
out+="FEATURE_DOCUMENT_COMMENTS=${FEATURE_DOCUMENT_COMMENTS}\n"
out+="FEATURE_RAG_QA=${FEATURE_RAG_QA}\n"
out+="FEATURE_SUMMARIZATION=${FEATURE_SUMMARIZATION}\n"
out+="FEATURE_ENTITY_EXTRACTION=${FEATURE_ENTITY_EXTRACTION}\n"
out+="FEATURE_ANNOTATIONS=${FEATURE_ANNOTATIONS}\n"
out+="FEATURE_SUBSCRIPTIONS=${FEATURE_SUBSCRIPTIONS}\n"
out+="FEATURE_EXPERTISE_MAP=${FEATURE_EXPERTISE_MAP}\n"
out+="FEATURE_RELATED_DOCS=${FEATURE_RELATED_DOCS}\n"
out+="FEATURE_AUTO_TAGGING=${FEATURE_AUTO_TAGGING}\n"
out+="AUTO_ENRICH_THRESHOLD=${AUTO_ENRICH_THRESHOLD}\n"
out+="INGEST_MODE=${INGEST_MODE}\n"
out+="\n"

out+="# Embedding provider\n"
out+="EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER}\n"
out+="EMBEDDING_MODEL=${EMBEDDING_MODEL}\n"
out+="EMBEDDING_URL=${EMBEDDING_URL}\n"
out+="EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD=${EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD}\n"
out+="\n"

out+="# Published ports\n"
out+="API_PORT=${API_PORT}\n"
out+="FRONTEND_PORT=${FRONTEND_PORT}\n"
out+="POSTGRES_PORT=${POSTGRES_PORT}\n"
out+="KAFKA_PORT=${KAFKA_PORT}\n"
out+="ELASTICSEARCH_PORT=${ELASTICSEARCH_PORT}\n"
out+="QDRANT_PORT=${QDRANT_PORT}\n"
out+="LIBRETRANSLATE_PORT=${LIBRETRANSLATE_PORT}\n"
out+="OLLAMA_PORT=${OLLAMA_PORT}\n"
out+="\n"

out+="# Persistent Docker volume names\n"
out+="TOMORROWLAND_FILES_VOLUME=${FILES_VOLUME}\n"
out+="TOMORROWLAND_POSTGRES_VOLUME=${POSTGRES_VOLUME}\n"
out+="TOMORROWLAND_KAFKA_VOLUME=${KAFKA_VOLUME}\n"
out+="TOMORROWLAND_ELASTICSEARCH_VOLUME=${ELASTICSEARCH_VOLUME}\n"
out+="TOMORROWLAND_QDRANT_VOLUME=${QDRANT_VOLUME}\n"
out+="TOMORROWLAND_LIBRETRANSLATE_VOLUME=${LIBRETRANSLATE_VOLUME}\n"
out+="TOMORROWLAND_OLLAMA_VOLUME=${OLLAMA_VOLUME}\n"
out+="TOMORROWLAND_PROMETHEUS_VOLUME=${PROMETHEUS_VOLUME}\n"
out+="TOMORROWLAND_GRAFANA_VOLUME=${GRAFANA_VOLUME}\n"
out+="\n"

if [[ "$AIRGAP" -eq 1 ]]; then
  out+="# Air-gapped images\n"
  out+="TOMORROWLAND_BACKEND_IMAGE=${BACKEND_IMAGE}\n"
  out+="TOMORROWLAND_FRONTEND_IMAGE=${FRONTEND_IMAGE}\n"
  out+="TOMORROWLAND_LIBRETRANSLATE_IMAGE=${LIBRETRANSLATE_IMAGE}\n"
  out+="\n"

  out+="# Folder connector host mount\n"
  out+="TOMORROWLAND_FOLDER_SOURCE_HOST_PATH=${FOLDER_SOURCE_HOST_PATH}\n"
  out+="TOMORROWLAND_FOLDER_SOURCE_CONTAINER_PATH=${FOLDER_SOURCE_CONTAINER_PATH}\n"
  out+="\n"
fi

# --- write or print ---

if [[ "$PRINT" -eq 1 ]]; then
  printf '%b' "$out"
  log "printed to stdout"
else
  printf '%b' "$out" > "$OUTPUT"
  chmod 600 "$OUTPUT"
  log "wrote $OUTPUT ($(wc -c < "$OUTPUT") bytes, mode 600)"
fi
