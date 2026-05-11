#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { printf '[upgrade-airgap] %s\n' "$*"; }
fail() { printf '[upgrade-airgap] ERROR: %s\n' "$*" >&2; rollback_guidance; exit 1; }
env_value() {
  key="$1"
  default="$2"
  if [[ -f .env ]]; then
    value="$(awk -F= -v key="$key" '
      $0 ~ /^[[:space:]]*#/ {next}
      $1 == key {sub(/^[^=]*=/, ""); gsub(/^"|"$/, ""); gsub(/^'"'"'|'"'"'$/, ""); print; exit}
    ' .env)"
    if [[ -n "$value" ]]; then
      printf '%s' "$value"
      return
    fi
  fi
  printf '%s' "$default"
}

usage() {
  cat <<'USAGE'
Usage: scripts/upgrade-airgap.sh --artifact-dir DIR [--skip-backup] [--backup-output-dir DIR]

Safely upgrade an existing Tomorrowland air-gapped Compose deployment with a newer
extracted release artifact. Run from the current deployment directory containing
.env. The script preserves data volumes, never overwrites .env, never pulls from
the internet, and never runs docker compose down -v.

Flow:
  1. Run read-only preflight.
  2. Create a backup unless --skip-backup is explicitly passed.
  3. Load local images from the artifact.
  4. Copy new release Compose files into the deployment directory.
  5. Stop services without removing volumes.
  6. Start PostgreSQL and run the migrate service/job.
  7. Start the upgraded stack and run basic health checks.

Options:
  --artifact-dir DIR       Extracted tomorrowland-release-<version> directory (required).
  --skip-backup            Dangerous override; continue without running backup.
  --backup-output-dir DIR  Parent directory for backup (default: ./backups).
  -h, --help               Show this help.
USAGE
}

artifact_dir=""
skip_backup=0
backup_output_dir="backups"
backup_dir=""

rollback_guidance() {
  cat >&2 <<GUIDANCE
[upgrade-airgap] Rollback guidance:
[upgrade-airgap]   1. Do not run 'docker compose down -v'.
[upgrade-airgap]   2. Keep services stopped if validation failed after migration.
[upgrade-airgap]   3. If a backup was created, review: ${backup_dir:-<backup directory not created>}
[upgrade-airgap]   4. Restore with: scripts/restore-airgap-data.sh --backup-dir <backup-dir> --confirm-restore
[upgrade-airgap]   5. Restore Elasticsearch/Qdrant volume snapshots if you took them, then start the previous stack.
GUIDANCE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir)
      [[ $# -ge 2 ]] || { printf '[upgrade-airgap] ERROR: --artifact-dir requires a directory\n' >&2; exit 1; }
      artifact_dir="$2"
      shift 2
      ;;
    --skip-backup)
      skip_backup=1
      shift
      ;;
    --backup-output-dir)
      [[ $# -ge 2 ]] || { printf '[upgrade-airgap] ERROR: --backup-output-dir requires a directory\n' >&2; exit 1; }
      backup_output_dir="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf '[upgrade-airgap] ERROR: unknown argument: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

[[ -n "$artifact_dir" ]] || { printf '[upgrade-airgap] ERROR: --artifact-dir is required\n' >&2; exit 1; }
[[ -d "$artifact_dir" ]] || { printf '[upgrade-airgap] ERROR: artifact directory not found: %s\n' "$artifact_dir" >&2; exit 1; }
[[ -f .env ]] || { printf '[upgrade-airgap] ERROR: run from deployment directory containing .env\n' >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { printf '[upgrade-airgap] ERROR: docker is required\n' >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { printf '[upgrade-airgap] ERROR: Docker Compose plugin is required\n' >&2; exit 1; }

log "running read-only preflight"
"$script_dir/preflight-upgrade-check.sh" --artifact-dir "$artifact_dir"

if [[ "$skip_backup" -eq 1 ]]; then
  log "WARNING: --skip-backup was provided; continuing without a fresh backup"
else
  before_list="$(mktemp)"
  after_list="$(mktemp)"
  find "$backup_output_dir" -maxdepth 1 -type d -name 'tomorrowland-airgap-backup-*' 2>/dev/null | sort > "$before_list" || true
  "$script_dir/backup-airgap-data.sh" --output-dir "$backup_output_dir"
  find "$backup_output_dir" -maxdepth 1 -type d -name 'tomorrowland-airgap-backup-*' 2>/dev/null | sort > "$after_list" || true
  backup_dir="$(comm -13 "$before_list" "$after_list" | tail -n 1 || true)"
  rm -f "$before_list" "$after_list"
  [[ -n "$backup_dir" ]] || fail "backup completed but new backup directory could not be detected"
  log "backup completed: $backup_dir"
fi

log "loading images from local artifact"
bash "$artifact_dir/scripts/load-airgap-images.sh" "$artifact_dir"

release_backup_dir=".upgrade-previous/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$release_backup_dir"
for file in docker-compose.airgap.yml docker-compose.yml release-manifest.json; do
  [[ -f "$file" ]] && cp "$file" "$release_backup_dir/$file"
done

log "installing new Compose files and upgrade helper scripts from artifact without touching .env"
mkdir -p scripts
for helper in load-airgap-images.sh validate-airgap-artifact.sh load-ollama-model-bundle.sh validate-ollama-model.sh preflight-upgrade-check.sh backup-airgap-data.sh restore-airgap-data.sh upgrade-airgap.sh; do
  [[ -f "$artifact_dir/scripts/$helper" ]] && cp "$artifact_dir/scripts/$helper" "scripts/$helper"
done
chmod +x scripts/*.sh
cp "$artifact_dir/docker-compose.airgap.yml" docker-compose.airgap.yml
[[ -f "$artifact_dir/docker-compose.yml" ]] && cp "$artifact_dir/docker-compose.yml" docker-compose.yml
[[ -f "$artifact_dir/release-manifest.json" ]] && cp "$artifact_dir/release-manifest.json" release-manifest.json

compose_cmd=(docker compose --env-file .env -f docker-compose.airgap.yml)

log "verifying expected image tags are loaded locally"
"${compose_cmd[@]}" config --images > /tmp/tomorrowland-upgrade-images.$$
while IFS= read -r image; do
  [[ -n "$image" ]] || continue
  docker image inspect "$image" >/dev/null || fail "required image is not loaded locally: $image"
done < /tmp/tomorrowland-upgrade-images.$$
rm -f /tmp/tomorrowland-upgrade-images.$$

log "stopping services safely without removing volumes"
"${compose_cmd[@]}" stop

log "starting PostgreSQL for migrations"
"${compose_cmd[@]}" up -d postgres

log "running database migrations; upgrade stops immediately if this fails"
if ! "${compose_cmd[@]}" run --rm migrate; then
  fail "database migrations failed; upgraded stack was not started"
fi

log "starting upgraded stack"
"${compose_cmd[@]}" up -d

api_port="$(env_value API_PORT 8000)"
frontend_port="$(env_value FRONTEND_PORT 8080)"
log "post-upgrade service status"
"${compose_cmd[@]}" ps

log "running basic post-upgrade health checks"
health_ok=0
if command -v curl >/dev/null 2>&1; then
  if curl -fsS "http://127.0.0.1:${api_port}/health" >/dev/null; then
    log "API /health responded"
    health_ok=$((health_ok + 1))
  else
    log "WARNING: API /health did not respond on 127.0.0.1:${api_port}; check service health and configured ports"
  fi
  if curl -fsS "http://127.0.0.1:${frontend_port}/health" >/dev/null; then
    log "frontend /health responded"
    health_ok=$((health_ok + 1))
  else
    log "WARNING: frontend /health did not respond on 127.0.0.1:${frontend_port}; check service health and configured ports"
  fi
else
  log "curl is not installed; skipping HTTP health checks"
fi

log "upgrade orchestration completed; ${health_ok}/2 basic HTTP health checks passed"
log "Complete the manual validation checklist in docs/operations/air-gapped-upgrade.md before declaring the upgrade successful."
