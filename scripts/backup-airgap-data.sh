#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_VERSION="1.0"

log() { printf '[backup-airgap-data] %s\n' "$*"; }
fail() { printf '[backup-airgap-data] ERROR: %s\n' "$*" >&2; exit 1; }
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
Usage: scripts/backup-airgap-data.sh [--output-dir DIR] [--compose-file FILE ...]

Create a timestamped, fail-closed backup for an existing Tomorrowland air-gapped
Compose deployment. Run from the deployment directory containing .env.

Backs up:
  - .env
  - active Compose files and local override files
  - current image references, Compose config, service state, Docker metadata
  - PostgreSQL dump from the running postgres Compose service
  - files_data named volume archive
  - Elasticsearch/Qdrant/monitoring restore strategy notes

Options:
  --output-dir DIR     Parent backup directory (default: ./backups).
  --compose-file FILE  Compose file in use. May be repeated. Defaults to
                       $COMPOSE_FILE, docker-compose.airgap.yml, or docker-compose.yml.
  -h, --help           Show this help.

The script never deletes data and never runs docker compose down -v.
USAGE
}

output_parent="backups"
compose_files=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      [[ $# -ge 2 ]] || fail "--output-dir requires a directory"
      output_parent="$2"
      shift 2
      ;;
    --compose-file|-f)
      [[ $# -ge 2 ]] || fail "--compose-file requires a file"
      compose_files+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ -f .env ]] || fail "run from an existing deployment directory containing .env"
command -v docker >/dev/null 2>&1 || fail "docker is required"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is required"
command -v tar >/dev/null 2>&1 || fail "tar is required"

if [[ ${#compose_files[@]} -eq 0 && -n "${COMPOSE_FILE:-}" ]]; then
  IFS=':' read -r -a compose_files <<< "${COMPOSE_FILE}"
fi
if [[ ${#compose_files[@]} -eq 0 ]]; then
  if [[ -f docker-compose.airgap.yml ]]; then
    compose_files+=("docker-compose.airgap.yml")
  elif [[ -f docker-compose.yml ]]; then
    compose_files+=("docker-compose.yml")
  else
    fail "no Compose file detected; pass --compose-file"
  fi
fi
for file in "${compose_files[@]}"; do
  [[ -f "$file" ]] || fail "Compose file missing: $file"
done

mkdir -p "$output_parent"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${output_parent%/}/tomorrowland-airgap-backup-${timestamp}"
[[ ! -e "$backup_dir" ]] || fail "backup directory already exists: $backup_dir"
mkdir -p "$backup_dir"/{config,metadata,postgres,files,notes,logs}
backup_abs="$(cd "$backup_dir" && pwd)"

cleanup_on_error() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    log "backup failed; partial backup retained for inspection: $backup_dir"
    printf 'Backup failed at %s UTC. Partial backup retained for inspection.\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$backup_dir/FAILED.txt" || true
  fi
  exit $rc
}
trap cleanup_on_error EXIT

compose_cmd=(docker compose --env-file .env)
for file in "${compose_files[@]}"; do
  compose_cmd+=(-f "$file")
done

log "writing backup to $backup_dir"
cp .env "$backup_dir/config/.env"
for file in "${compose_files[@]}"; do
  cp "$file" "$backup_dir/config/$(basename "$file")"
done
shopt -s nullglob
for file in docker-compose.override.yml compose.override.yml *.local.yml .env.local; do
  [[ -f "$file" ]] && cp "$file" "$backup_dir/config/$(basename "$file")"
done
shopt -u nullglob

{
  printf 'backup_script_version=%s\n' "$SCRIPT_VERSION"
  printf 'created_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'deployment_dir=%s\n' "$(pwd)"
  printf 'compose_files=%s\n' "${compose_files[*]}"
  printf 'compose_project_name=%s\n' "$(env_value COMPOSE_PROJECT_NAME "$(basename "$(pwd)")")"
} > "$backup_dir/metadata/backup.properties"

docker version > "$backup_dir/metadata/docker-version.txt" 2>&1 || true
docker compose version > "$backup_dir/metadata/docker-compose-version.txt" 2>&1 || true
"${compose_cmd[@]}" ps > "$backup_dir/metadata/compose-ps.txt" 2>&1 || true
"${compose_cmd[@]}" config > "$backup_dir/metadata/compose.rendered.yml" 2> "$backup_dir/logs/compose-config.stderr.log"
"${compose_cmd[@]}" config --images > "$backup_dir/metadata/current-images.txt" 2> "$backup_dir/logs/compose-images.stderr.log"
"${compose_cmd[@]}" config --volumes > "$backup_dir/metadata/current-volumes.txt" 2> "$backup_dir/logs/compose-volumes.stderr.log" || true

postgres_user="$(env_value POSTGRES_USER postgres)"
postgres_db="$(env_value POSTGRES_DB app)"
log "dumping PostgreSQL database $postgres_db from compose service postgres"
if ! "${compose_cmd[@]}" exec -T postgres pg_dump -U "$postgres_user" -d "$postgres_db" --format=custom --no-owner --no-privileges > "$backup_dir/postgres/postgres.dump" 2> "$backup_dir/logs/postgres-dump.stderr.log"; then
  fail "PostgreSQL dump failed; see $backup_dir/logs/postgres-dump.stderr.log"
fi
[[ -s "$backup_dir/postgres/postgres.dump" ]] || fail "PostgreSQL dump is empty"

project_name="$(env_value COMPOSE_PROJECT_NAME "$(basename "$(pwd)")")"
files_volume="${project_name}_files_data"
if ! docker volume inspect "$files_volume" >/dev/null 2>&1; then
  alt_volume="$("${compose_cmd[@]}" config --volumes 2>/dev/null | awk '/^files_data$/ {print "files_data"; exit}')"
  if [[ -n "$alt_volume" ]] && docker volume inspect "$alt_volume" >/dev/null 2>&1; then
    files_volume="$alt_volume"
  fi
fi

tar_image="${BACKUP_TAR_IMAGE:-postgres:16-alpine}"
log "archiving files volume $files_volume with local image $tar_image"
if docker volume inspect "$files_volume" >/dev/null 2>&1; then
  if ! docker run --rm \
      -v "${files_volume}:/data:ro" \
      -v "${backup_abs}:/backup" \
      "$tar_image" \
      sh -c 'cd /data && tar czf /backup/files/files_data.tar.gz .' \
      > "$backup_dir/logs/files-archive.stdout.log" \
      2> "$backup_dir/logs/files-archive.stderr.log"; then
    fail "files volume archive failed; see $backup_dir/logs/files-archive.stderr.log"
  fi
else
  fail "files_data volume not found as $files_volume; refusing to continue with an incomplete backup"
fi
[[ -s "$backup_dir/files/files_data.tar.gz" ]] || fail "files archive is empty"

cat > "$backup_dir/notes/elasticsearch-qdrant-restore-strategy.md" <<'NOTES'
# Elasticsearch and Qdrant backup/restore strategy

This backup script records Compose metadata and preserves PostgreSQL plus the
Tomorrowland files volume. It does not automate live Elasticsearch or Qdrant
snapshots because snapshot repository setup is deployment-specific and should not
write secrets or host paths into release tooling.

Safe fallback before a high-risk upgrade:

1. Run `scripts/backup-airgap-data.sh` successfully.
2. Stop services without deleting volumes: `docker compose --env-file .env -f docker-compose.airgap.yml stop`.
3. Take storage-level snapshots or offline archives of the named volumes listed in
   `metadata/current-volumes.txt`, especially `elasticsearch_data` and `qdrant_data`.
4. Start services again only after volume snapshots complete.

Never run `docker compose down -v`; it deletes persistent product data.
NOTES

cat > "$backup_dir/notes/monitoring-backup-guidance.md" <<'NOTES'
# Optional monitoring data

If a monitoring Compose profile is present in this deployment, back up Prometheus
and Grafana named volumes or bind-mounted data directories with the same offline
storage snapshot process used for Elasticsearch and Qdrant. Do not place Grafana
admin passwords, API tokens, or private keys in backup notes or manifests.
NOTES

printf 'Backup completed successfully at %s UTC.\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$backup_dir/SUCCESS.txt"
trap - EXIT
log "backup completed successfully: $backup_dir"
