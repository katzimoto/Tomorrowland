#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_VERSION="1.0"

pass() { printf '[preflight-upgrade-check] PASS: %s\n' "$*"; }
warn() { printf '[preflight-upgrade-check] WARN: %s\n' "$*"; }
info() { printf '[preflight-upgrade-check] INFO: %s\n' "$*"; }
fail_msg() { printf '[preflight-upgrade-check] FAIL: %s\n' "$*" >&2; failures=$((failures + 1)); }
fatal() { printf '[preflight-upgrade-check] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/preflight-upgrade-check.sh [--artifact-dir DIR] [--compose-file FILE ...]

Read-only preflight for upgrading an existing Tomorrowland air-gapped deployment.
Run from the current deployment directory. The script validates the current
.env and Compose path, checks Docker/Compose availability, verifies a new
release artifact, confirms checksums when present, rejects required build steps,
and proves every air-gapped Compose image is bundled or already present locally.

Options:
  --artifact-dir DIR       Extracted tomorrowland-release-<version> directory.
                           Defaults to $TOMORROWLAND_RELEASE_ARTIFACT or ../tomorrowland-release-*.
  --compose-file FILE      Current deployment Compose file. May be repeated.
                           Defaults to $COMPOSE_FILE, docker-compose.airgap.yml,
                           or docker-compose.yml in the deployment directory.
  -h, --help               Show this help.

This script is read-only: it never starts, stops, loads, deletes, or rewrites
services, data, volumes, images, or configuration.
USAGE
}

failures=0
artifact_dir="${TOMORROWLAND_RELEASE_ARTIFACT:-}"
compose_files=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir)
      [[ $# -ge 2 ]] || fatal "--artifact-dir requires a directory"
      artifact_dir="$2"
      shift 2
      ;;
    --compose-file|-f)
      [[ $# -ge 2 ]] || fatal "--compose-file requires a file"
      compose_files+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fatal "unknown argument: $1"
      ;;
  esac
done

if [[ ${#compose_files[@]} -eq 0 && -n "${COMPOSE_FILE:-}" ]]; then
  IFS=':' read -r -a compose_files <<< "${COMPOSE_FILE}"
fi
if [[ ${#compose_files[@]} -eq 0 ]]; then
  if [[ -f docker-compose.airgap.yml ]]; then
    compose_files+=("docker-compose.airgap.yml")
  elif [[ -f docker-compose.yml ]]; then
    compose_files+=("docker-compose.yml")
  fi
fi

if [[ -z "$artifact_dir" ]]; then
  shopt -s nullglob
  candidates=(../tomorrowland-release-* ./tomorrowland-release-*)
  shopt -u nullglob
  if [[ ${#candidates[@]} -eq 1 && -d "${candidates[0]}" ]]; then
    artifact_dir="${candidates[0]}"
  fi
fi

info "preflight script version: $SCRIPT_VERSION"
if [[ -f .env ]]; then
  pass "deployment .env exists"
else
  fail_msg "run from an existing deployment directory containing .env"
fi
if [[ ${#compose_files[@]} -gt 0 ]]; then
  pass "detected compose files: ${compose_files[*]}"
else
  fail_msg "no compose file detected; pass --compose-file"
fi
for file in "${compose_files[@]}"; do
  if [[ -f "$file" ]]; then
    pass "compose file exists: $file"
  else
    fail_msg "compose file missing: $file"
  fi
done

if command -v docker >/dev/null 2>&1; then
  pass "docker CLI is installed"
  if docker version --format '{{.Server.Version}}' >/tmp/tomorrowland-docker-version.$$ 2>/tmp/tomorrowland-docker-version-err.$$; then
    pass "Docker Engine is available: $(cat /tmp/tomorrowland-docker-version.$$)"
  else
    fail_msg "Docker Engine is not available: $(cat /tmp/tomorrowland-docker-version-err.$$)"
  fi
  rm -f /tmp/tomorrowland-docker-version.$$ /tmp/tomorrowland-docker-version-err.$$

  if docker compose version >/tmp/tomorrowland-compose-version.$$ 2>/tmp/tomorrowland-compose-version-err.$$; then
    pass "Docker Compose plugin is available: $(cat /tmp/tomorrowland-compose-version.$$)"
  else
    fail_msg "Docker Compose plugin is not available: $(cat /tmp/tomorrowland-compose-version-err.$$)"
  fi
  rm -f /tmp/tomorrowland-compose-version.$$ /tmp/tomorrowland-compose-version-err.$$
else
  fail_msg "docker CLI is not installed"
fi

compose_cmd=(docker compose --env-file .env)
for file in "${compose_files[@]}"; do
  compose_cmd+=(-f "$file")
done

if command -v docker >/dev/null 2>&1 && [[ ${#compose_files[@]} -gt 0 && -f .env ]]; then
  if "${compose_cmd[@]}" ps --format 'table {{.Name}}\t{{.Service}}\t{{.State}}\t{{.Image}}' >/tmp/tomorrowland-compose-ps.$$ 2>/tmp/tomorrowland-compose-ps-err.$$; then
    info "current service state:"
    sed 's/^/[preflight-upgrade-check]   /' /tmp/tomorrowland-compose-ps.$$
  else
    warn "could not query current service state: $(cat /tmp/tomorrowland-compose-ps-err.$$)"
  fi
  rm -f /tmp/tomorrowland-compose-ps.$$ /tmp/tomorrowland-compose-ps-err.$$

  if [[ -f release-manifest.json ]]; then
    current_version="$(awk -F'"' '/"release_version"[[:space:]]*:/ {print $4; exit}' release-manifest.json)"
    [[ -n "$current_version" ]] && info "current release-manifest version: $current_version"
  elif [[ -f .env ]]; then
    current_version="$(awk -F= '$1 == "APP_VERSION" {print $2; exit}' .env)"
    [[ -n "$current_version" ]] && info "current APP_VERSION from .env: $current_version"
  fi

  if "${compose_cmd[@]}" config --images >/tmp/tomorrowland-current-images.$$ 2>/tmp/tomorrowland-current-images-err.$$; then
    info "current image references:"
    sed 's/^/[preflight-upgrade-check]   /' /tmp/tomorrowland-current-images.$$
  else
    warn "could not render current image references: $(cat /tmp/tomorrowland-current-images-err.$$)"
  fi
  rm -f /tmp/tomorrowland-current-images.$$ /tmp/tomorrowland-current-images-err.$$

  if "${compose_cmd[@]}" config --volumes >/tmp/tomorrowland-current-volumes.$$ 2>/tmp/tomorrowland-current-volumes-err.$$; then
    info "current expected named volumes:"
    sed 's/^/[preflight-upgrade-check]   /' /tmp/tomorrowland-current-volumes.$$
    project_name="$(awk -F= '$1 == "COMPOSE_PROJECT_NAME" {print $2; exit}' .env)"
    project_name="${project_name:-$(basename "$(pwd)")}"
    while IFS= read -r volume; do
      [[ -n "$volume" ]] || continue
      if docker volume inspect "${project_name}_${volume}" >/dev/null 2>&1; then
        pass "persistent volume exists: ${project_name}_${volume}"
      elif docker volume inspect "$volume" >/dev/null 2>&1; then
        pass "persistent volume exists: $volume"
      else
        warn "persistent volume not found yet: ${project_name}_${volume} (or $volume); verify project name before upgrade"
      fi
    done < /tmp/tomorrowland-current-volumes.$$
  else
    warn "could not render current volume references: $(cat /tmp/tomorrowland-current-volumes-err.$$)"
  fi
  rm -f /tmp/tomorrowland-current-volumes.$$ /tmp/tomorrowland-current-volumes-err.$$

  folder_path="$(awk -F= '$1 == "TOMORROWLAND_FOLDER_SOURCE_HOST_PATH" {print $2; exit}' .env)"
  if [[ -n "$folder_path" ]]; then
    if [[ -e "$folder_path" ]]; then
      pass "folder source host path exists: $folder_path"
    else
      warn "folder source host path is configured but not present: $folder_path"
    fi
  fi
fi

if [[ -z "$artifact_dir" ]]; then
  fail_msg "new release artifact directory not provided; pass --artifact-dir"
else
  if [[ -d "$artifact_dir" ]]; then
    pass "artifact directory exists: $artifact_dir"
  else
    fail_msg "artifact directory missing: $artifact_dir"
  fi
fi

if [[ -n "$artifact_dir" && -d "$artifact_dir" ]]; then
  required_artifact_files=(
    "docker-compose.airgap.yml"
    ".env.airgap.example"
    "images/tomorrowland-images.tar"
    "scripts/load-airgap-images.sh"
    "scripts/validate-airgap-artifact.sh"
    "scripts/load-ollama-model-bundle.sh"
    "scripts/validate-ollama-model.sh"
    "checksums.txt"
    "release-manifest.json"
  )
  for file in "${required_artifact_files[@]}"; do
    if [[ -f "${artifact_dir}/${file}" ]]; then
      pass "artifact contains $file"
    else
      fail_msg "artifact missing required file: $file"
    fi
  done

  if [[ -f "${artifact_dir}/checksums.txt" ]]; then
    if (cd "$artifact_dir" && sha256sum -c checksums.txt >/tmp/tomorrowland-checksums.$$ 2>/tmp/tomorrowland-checksums-err.$$); then
      pass "artifact checksums are valid"
    else
      fail_msg "artifact checksums failed: $(cat /tmp/tomorrowland-checksums-err.$$)"
    fi
    rm -f /tmp/tomorrowland-checksums.$$ /tmp/tomorrowland-checksums-err.$$
  fi

  if [[ -f "${artifact_dir}/release-manifest.json" ]]; then
    for key in release_version git_commit created_at images compose_files minimum_docker_version minimum_compose_version migrations persistent_data backup_restore_script_version; do
      if grep -Eq "\"${key}\"[[:space:]]*:" "${artifact_dir}/release-manifest.json"; then
        pass "release manifest includes $key"
      else
        fail_msg "release manifest missing key: $key"
      fi
    done
  fi

  if command -v docker >/dev/null 2>&1 && [[ -f "${artifact_dir}/docker-compose.airgap.yml" && -f "${artifact_dir}/.env.airgap.example" ]]; then
    tmp_dir="$(mktemp -d)"
    # shellcheck disable=SC2317 # invoked by EXIT trap
    cleanup() { rm -rf "$tmp_dir"; }
    trap cleanup EXIT

    if docker compose --env-file "${artifact_dir}/.env.airgap.example" -f "${artifact_dir}/docker-compose.airgap.yml" config > "$tmp_dir/compose.rendered.yml" 2>"$tmp_dir/compose.err"; then
      pass "artifact air-gapped compose config is valid"
    else
      fail_msg "artifact air-gapped compose config failed: $(cat "$tmp_dir/compose.err")"
    fi

    if grep -Eq '^[[:space:]]+build:' "${artifact_dir}/docker-compose.airgap.yml" "$tmp_dir/compose.rendered.yml" 2>/dev/null; then
      fail_msg "air-gapped compose path contains a build step"
    else
      pass "air-gapped compose path has no build steps"
    fi

    if docker compose --env-file "${artifact_dir}/.env.airgap.example" -f "${artifact_dir}/docker-compose.airgap.yml" config --images > "$tmp_dir/images.txt" 2>"$tmp_dir/images.err"; then
      pass "artifact image list rendered"
      if [[ -f "${artifact_dir}/images/tomorrowland-images.tar" ]] && tar -xOf "${artifact_dir}/images/tomorrowland-images.tar" manifest.json > "$tmp_dir/docker-manifest.json" 2>/dev/null; then
        bundled_missing=0
        while IFS= read -r image; do
          [[ -n "$image" ]] || continue
          if grep -Fq "\"$image\"" "$tmp_dir/docker-manifest.json"; then
            printf '[preflight-upgrade-check] PASS: bundled image: %s\n' "$image"
          elif docker image inspect "$image" >/dev/null 2>&1; then
            printf '[preflight-upgrade-check] PASS: image already present locally: %s\n' "$image"
          else
            printf '[preflight-upgrade-check] FAIL: image not bundled or local: %s\n' "$image" >&2
            bundled_missing=1
          fi
        done < "$tmp_dir/images.txt"
        [[ "$bundled_missing" -eq 0 ]] || fail_msg "one or more artifact images are missing"
      else
        fail_msg "image bundle is missing or does not contain Docker manifest.json"
      fi
    else
      fail_msg "could not render artifact image list: $(cat "$tmp_dir/images.err")"
    fi
  fi
fi

if [[ "$failures" -eq 0 ]]; then
  pass "preflight completed successfully; no changes were made"
  exit 0
fi

printf '[preflight-upgrade-check] SUMMARY: %s failure(s); no changes were made\n' "$failures" >&2
exit 1
