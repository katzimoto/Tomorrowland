#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[load-ollama-model-bundle] %s\n' "$*"; }
fail() { printf '[load-ollama-model-bundle] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/load-ollama-model-bundle.sh --bundle <path> --compose-file <path> --env-file <path> [--project-name <name>]

Load a Tomorrowland Ollama model bundle into the Compose ollama_data volume.
This script is non-destructive: it does not run docker compose down -v and it
copies bundle model files into the target volume without deleting existing models.
USAGE
}

bundle=""
compose_file=""
env_file=""
project_name=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)
      bundle="${2:-}"; shift 2 ;;
    --compose-file)
      compose_file="${2:-}"; shift 2 ;;
    --env-file)
      env_file="${2:-}"; shift 2 ;;
    --project-name)
      project_name="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      fail "unknown argument: $1" ;;
  esac
done

[[ -n "$bundle" ]] || fail "--bundle is required"
[[ -n "$compose_file" ]] || fail "--compose-file is required"
[[ -n "$env_file" ]] || fail "--env-file is required"
[[ -f "$bundle" ]] || fail "bundle archive not found: $bundle"
[[ -f "$compose_file" ]] || fail "compose file not found: $compose_file"
[[ -f "$env_file" ]] || fail "env file not found: $env_file"

command -v docker >/dev/null 2>&1 || fail "docker with the Compose plugin is required"
command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

docker info >/dev/null 2>&1 || fail "Docker daemon is not reachable"

tmp_dir="$(mktemp -d)"
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT

log "Extracting bundle: $bundle"
tar -xzf "$bundle" -C "$tmp_dir"
mapfile -t roots < <(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | sort)
[[ "${#roots[@]}" -eq 1 ]] || fail "bundle must contain exactly one top-level directory"
bundle_root="${roots[0]}"

[[ -d "$bundle_root/models" ]] || fail "bundle is missing models/"
[[ -f "$bundle_root/model-manifest.json" ]] || fail "bundle is missing model-manifest.json"
[[ -f "$bundle_root/checksums.txt" ]] || fail "bundle is missing checksums.txt"

log "Validating bundle checksums"
(
  cd "$bundle_root"
  sha256sum -c checksums.txt >/dev/null
)

model="$(python3 - "$bundle_root/model-manifest.json" <<'PY'
from __future__ import annotations
import json, sys
manifest = json.load(open(sys.argv[1], encoding='utf-8'))
print(manifest.get('expected_env', {}).get('OLLAMA_MODEL') or manifest.get('requested_model') or '')
PY
)"
[[ -n "$model" ]] || fail "model-manifest.json does not identify expected OLLAMA_MODEL"
log "Bundle model: $model"

if [[ -z "$project_name" ]]; then
  env_project_name="$(awk -F= '/^[[:space:]]*COMPOSE_PROJECT_NAME[[:space:]]*=/ {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' "$env_file")"
  if [[ -n "$env_project_name" ]]; then
    project_name="$env_project_name"
  else
    # Match docker compose's default project name: the compose file directory basename.
    compose_dir="$(cd "$(dirname "$compose_file")" && pwd)"
    project_name="$(basename "$compose_dir" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_-]+//g')"
  fi
fi
[[ -n "$project_name" ]] || fail "could not determine Compose project name; pass --project-name"
compose_args=(-p "$project_name" --env-file "$env_file" -f "$compose_file")
volume_name="${project_name}_ollama_data"

log "Ensuring target Docker volume exists: $volume_name"
docker volume inspect "$volume_name" >/dev/null 2>&1 || docker volume create "$volume_name" >/dev/null

log "Stopping Ollama service before copying model files (volumes preserved)"
docker compose "${compose_args[@]}" stop ollama >/dev/null 2>&1 || log "Ollama service was not running or could not be stopped; continuing"

ollama_image="$(docker compose "${compose_args[@]}" config --images | awk '/ollama/ {print; exit}')"
[[ -n "$ollama_image" ]] || ollama_image="ollama/ollama:latest"

log "Copying model files into $volume_name with local image $ollama_image (non-destructive merge)"
docker run --rm \
  -v "$volume_name:/target" \
  -v "$bundle_root/models:/bundle-models:ro" \
  "$ollama_image" \
  sh -c 'mkdir -p /target/models && cp -a /bundle-models/. /target/models/' >/dev/null

log "Starting Ollama service"
docker compose "${compose_args[@]}" up -d ollama >/dev/null

cat <<NEXT
[load-ollama-model-bundle] Model bundle loaded.
[load-ollama-model-bundle] Next validation command:
  OLLAMA_URL=http://localhost:\${OLLAMA_PORT:-11434} OLLAMA_MODEL=${model} bash scripts/validate-ollama-model.sh --smoke-test
NEXT
