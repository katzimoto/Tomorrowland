#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { printf '[tomorrowland-airgap] %s\n' "$*"; }
warn() { printf '[tomorrowland-airgap] WARNING: %s\n' "$*" >&2; }
fail() { printf '[tomorrowland-airgap] ERROR: %s\n' "$*" >&2; exit 1; }

env_value() {
  local key="$1" default="$2"
  if [[ -f .env ]]; then
    local value
    value="$(awk -F= -v key="$key" '
      $0 ~ /^[[:space:]]*#/ { next }
      $1 == key { sub(/^[^=]*=/, ""); gsub(/^"|"$/, ""); gsub(/^'"'"'|'"'"'$/, ""); print; exit }
    ' .env)"
    [[ -n "$value" ]] && { printf '%s' "$value"; return; }
  fi
  printf '%s' "$default"
}

usage() {
  cat <<'USAGE'
Usage: scripts/tomorrowland-airgap.sh <command> [options]

Tomorrowland air-gapped deployment wrapper. Run from the extracted release
directory (the directory containing docker-compose.airgap.yml).

Happy path (after downloading and verifying all release files):

  sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
  sha256sum -c tomorrowland-images-<version>.tar.parts.sha256
  tar xzf tomorrowland-release-<version>.tar.gz
  cd tomorrowland-release-<version>
  cp .env.airgap.example .env
  nano .env
  ./scripts/tomorrowland-airgap.sh validate --load-images
  ./scripts/tomorrowland-airgap.sh up

Commands:
  validate [--load-images] [--image-parts-dir DIR]
      Validate platform archive structure, checksums, compose config, and image
      bundle metadata. With --load-images, also loads Docker images from split
      parts or the embedded tar, then confirms all Compose images are present
      in the local Docker daemon. The operator does not need to manually
      reassemble split parts.

  load-images [--image-parts-dir DIR]
      Load Docker images from split tomorrowland-images-<version>.tar.part-*
      files auto-detected beside the release directory, or from the legacy
      embedded images/tomorrowland-images.tar. Streams parts into docker load;
      operator does not need to manually cat or reassemble the parts.

  up
      Start the Tomorrowland stack using the air-gapped Compose file. Requires
      .env to exist. Never overwrites .env or deletes volumes.

  status
      Show Docker Compose service status and print configured endpoint URLs.

  down
      Stop the Tomorrowland stack safely. Volumes are always preserved.
      Never runs docker compose down -v.

  backup [--output-dir DIR] [--compose-file FILE]
      Create a timestamped backup (PostgreSQL dump, files volume, config).
      Delegates to scripts/backup-airgap-data.sh. Pass --help for full options.

  upgrade --artifact-dir DIR [--skip-backup] [--backup-output-dir DIR]
      Upgrade an existing deployment with a newer extracted release artifact.
      Preserves .env and volumes. Delegates to scripts/upgrade-airgap.sh.
      Run from the existing deployment directory, not the new artifact directory.
      Pass --help for full options.

  help
      Show this help.

Options:
  --image-parts-dir DIR  Directory containing split tomorrowland-images-*.tar.part-*
                         files. Defaults to the parent directory of the release
                         directory (where image parts are placed beside the
                         platform archive after extraction).

Never run docker compose down -v. The -v flag deletes named volumes including
PostgreSQL, Elasticsearch, Qdrant, files, and Ollama data.
USAGE
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  validate)
    load_images=0
    image_parts_dir_arg=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --load-images) load_images=1; shift ;;
        --image-parts-dir)
          [[ $# -ge 2 ]] || fail "--image-parts-dir requires a directory argument"
          image_parts_dir_arg="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown argument for validate: $1  Run './scripts/tomorrowland-airgap.sh help' for usage." ;;
      esac
    done
    validate_args=()
    [[ "$load_images" -eq 1 ]] && validate_args+=(--load-images)
    [[ -n "$image_parts_dir_arg" ]] && validate_args+=(--image-parts-dir "$image_parts_dir_arg")
    validate_args+=(.)
    log "Running artifact validation"
    exec "$script_dir/validate-airgap-artifact.sh" "${validate_args[@]}"
    ;;

  load-images)
    image_parts_dir_arg=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --image-parts-dir)
          [[ $# -ge 2 ]] || fail "--image-parts-dir requires a directory argument"
          image_parts_dir_arg="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown argument for load-images: $1  Run './scripts/tomorrowland-airgap.sh help' for usage." ;;
      esac
    done
    load_args=()
    [[ -n "$image_parts_dir_arg" ]] && load_args+=(--image-parts-dir "$image_parts_dir_arg")
    load_args+=(.)
    log "Loading Docker images"
    exec "$script_dir/load-airgap-images.sh" "${load_args[@]}"
    ;;

  up)
    [[ $# -eq 0 ]] || fail "unexpected arguments for up: $*  Run './scripts/tomorrowland-airgap.sh help' for usage."
    [[ -f .env ]] || fail ".env not found.  Copy .env.airgap.example to .env and replace every 'change-me-*' placeholder before starting."
    [[ -f docker-compose.airgap.yml ]] || fail "docker-compose.airgap.yml not found.  Run from the extracted release directory."
    command -v docker >/dev/null 2>&1 || fail "docker is required"
    log "Starting Tomorrowland stack (air-gapped, no pull, no build)"
    exec docker compose --env-file .env -f docker-compose.airgap.yml up -d
    ;;

  status)
    [[ $# -eq 0 ]] || fail "unexpected arguments for status: $*  Run './scripts/tomorrowland-airgap.sh help' for usage."
    [[ -f docker-compose.airgap.yml ]] || fail "docker-compose.airgap.yml not found.  Run from the extracted release directory."
    command -v docker >/dev/null 2>&1 || fail "docker is required"
    if [[ -f .env ]]; then
      docker compose --env-file .env -f docker-compose.airgap.yml ps
      api_port="$(env_value API_PORT 8000)"
      frontend_port="$(env_value FRONTEND_PORT 8080)"
    else
      warn ".env not found; showing status with defaults"
      docker compose -f docker-compose.airgap.yml ps
      api_port="8000"
      frontend_port="8080"
    fi
    log "Frontend:  http://localhost:${frontend_port}"
    log "API:       http://localhost:${api_port}"
    ;;

  down)
    [[ $# -eq 0 ]] || fail "unexpected arguments for down: $*  Run './scripts/tomorrowland-airgap.sh help' for usage."
    [[ -f docker-compose.airgap.yml ]] || fail "docker-compose.airgap.yml not found.  Run from the extracted release directory."
    command -v docker >/dev/null 2>&1 || fail "docker is required"
    log "Stopping Tomorrowland stack (volumes preserved; never use 'down -v')"
    if [[ -f .env ]]; then
      exec docker compose --env-file .env -f docker-compose.airgap.yml down
    else
      exec docker compose -f docker-compose.airgap.yml down
    fi
    ;;

  backup)
    log "Delegating to backup-airgap-data.sh"
    exec "$script_dir/backup-airgap-data.sh" "$@"
    ;;

  upgrade)
    log "Delegating to upgrade-airgap.sh"
    exec "$script_dir/upgrade-airgap.sh" "$@"
    ;;

  help|-h|--help)
    usage
    exit 0
    ;;

  *)
    fail "unknown command: ${cmd}  Run './scripts/tomorrowland-airgap.sh help' for usage."
    ;;
esac
