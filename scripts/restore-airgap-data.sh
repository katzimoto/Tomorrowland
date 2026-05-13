#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[restore-airgap-data] %s\n' "$*"; }
fail() { printf '[restore-airgap-data] ERROR: %s\n' "$*" >&2; exit 1; }
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
Usage: scripts/restore-airgap-data.sh --backup-dir DIR --confirm-restore [--compose-file FILE ...]

Restore operator configuration, PostgreSQL, and the Tomorrowland files volume from
a backup created by scripts/backup-airgap-data.sh. This is intentionally
conservative and requires --confirm-restore because database and files-volume
restore actions replace current runtime state with backup contents.

Options:
  --backup-dir DIR       Backup directory to restore from (required).
  --confirm-restore      Required confirmation flag.
  --compose-file FILE    Compose file to use after restoring config. May be repeated.
                         Defaults to backed-up docker-compose.airgap.yml or docker-compose.yml.
  -h, --help             Show this help.

The script never deletes Docker volumes and never runs docker compose down -v.
It may stop services and replace data inside the existing PostgreSQL database and
files volume after explicit confirmation.
USAGE
}

backup_dir=""
confirmed=0
compose_files=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-dir)
      [[ $# -ge 2 ]] || fail "--backup-dir requires a directory"
      backup_dir="$2"
      shift 2
      ;;
    --confirm-restore)
      confirmed=1
      shift
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

[[ -n "$backup_dir" ]] || fail "--backup-dir is required"
[[ "$confirmed" -eq 1 ]] || fail "refusing restore without --confirm-restore"
[[ -d "$backup_dir" ]] || fail "backup directory not found: $backup_dir"
[[ -f "$backup_dir/SUCCESS.txt" ]] || fail "backup does not contain SUCCESS.txt; refusing ambiguous restore"
[[ -f "$backup_dir/config/.env" ]] || fail "backup is missing config/.env"
[[ -f "$backup_dir/postgres/postgres.dump" ]] || fail "backup is missing postgres/postgres.dump"
[[ -f "$backup_dir/files/files_data.tar.gz" ]] || fail "backup is missing files/files_data.tar.gz"
command -v docker >/dev/null 2>&1 || fail "docker is required"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is required"

log "WARNING: this restore will overwrite .env, restore backed-up Compose files, replace PostgreSQL contents, and replace files volume contents."
log "WARNING: Elasticsearch and Qdrant restore is guided in backup notes and is not automated by this script."
log "Safety invariant: this script will not delete Docker volumes and will not run docker compose down -v."

cp "$backup_dir/config/.env" .env
shopt -s nullglob
for file in "$backup_dir"/config/docker-compose*.yml "$backup_dir"/config/compose*.yml; do
  cp "$file" "$(basename "$file")"
done
shopt -u nullglob

if [[ ${#compose_files[@]} -eq 0 ]]; then
  if [[ -f docker-compose.airgap.yml ]]; then
    compose_files+=("docker-compose.airgap.yml")
  elif [[ -f docker-compose.yml ]]; then
    compose_files+=("docker-compose.yml")
  else
    fail "no restored Compose file found; pass --compose-file"
  fi
fi
for file in "${compose_files[@]}"; do
  [[ -f "$file" ]] || fail "Compose file missing after config restore: $file"
done

compose_cmd=(docker compose --env-file .env)
for file in "${compose_files[@]}"; do
  compose_cmd+=(-f "$file")
done

log "stopping application services without removing volumes"
"${compose_cmd[@]}" stop api frontend migrate kafka elasticsearch qdrant libretranslate ollama || true
log "starting PostgreSQL only for database restore"
"${compose_cmd[@]}" up -d postgres

postgres_user="$(env_value POSTGRES_USER postgres)"
postgres_db="$(env_value POSTGRES_DB app)"
log "restoring PostgreSQL database $postgres_db"
"${compose_cmd[@]}" exec -T postgres pg_restore \
  -U "$postgres_user" \
  -d "$postgres_db" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges < "$backup_dir/postgres/postgres.dump"

project_name="$(env_value COMPOSE_PROJECT_NAME "$(basename "$(pwd)")")"
files_volume="$(env_value TOMORROWLAND_FILES_VOLUME "tomorrowland_files_data")"
if ! docker volume inspect "$files_volume" >/dev/null 2>&1; then
  fail "files volume not found: $files_volume; create/start the stack once before restoring files"
fi

tar_image="${RESTORE_TAR_IMAGE:-postgres:16-alpine}"
backup_abs="$(cd "$backup_dir" && pwd)"
log "replacing contents of files volume $files_volume from backup archive"
docker run --rm \
  -v "${files_volume}:/data" \
  -v "${backup_abs}:/backup:ro" \
  "$tar_image" \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && cd /data && tar xzf /backup/files/files_data.tar.gz'

log "restore completed for .env, Compose files, PostgreSQL, and files_data"
log "Before starting the full stack, restore Elasticsearch/Qdrant volume snapshots if you took them. See: $backup_dir/notes/elasticsearch-qdrant-restore-strategy.md"
log "Start when ready: docker compose --env-file .env ${compose_files[*]/#/-f } up -d"
