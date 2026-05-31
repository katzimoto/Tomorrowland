#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[validate-airgap-artifact] %s\n' "$*"; }
fail() { printf '[validate-airgap-artifact] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/validate-airgap-artifact.sh [--load-images] [--image-parts-dir DIR] [artifact-directory]

Validate an extracted Tomorrowland air-gapped release artifact.
Checks required files, checksums, compose rendering, forbidden build steps, and
that every image referenced by docker-compose.airgap.yml exists in the offline
Docker image bundle. With --load-images, also docker-loads the bundle and verifies
image presence in the local Docker daemon.

The image bundle can be either:
  - images/tomorrowland-images.tar inside the artifact directory; or
  - split parts named tomorrowland-images-<version>.tar.part-* beside the artifact.
USAGE
}

load_images=0
image_parts_dir=""
artifact_dir="$(pwd)"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --load-images)
      load_images=1
      shift
      ;;
    --image-parts-dir)
      [[ $# -ge 2 ]] || fail "--image-parts-dir requires a directory"
      image_parts_dir="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      artifact_dir="$1"
      shift
      ;;
  esac
done

command -v docker >/dev/null 2>&1 || fail "docker with the Compose plugin is required"
command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

required_files=(
  "docker-compose.yml"
  "docker-compose.airgap.yml"
  ".env.airgap.example"
  "scripts/tomorrowland-airgap.sh"
  "scripts/load-airgap-images.sh"
  "scripts/validate-airgap-artifact.sh"
  "scripts/validate-translation-languages.sh"
  "scripts/preflight-upgrade-check.sh"
  "scripts/backup-airgap-data.sh"
  "scripts/restore-airgap-data.sh"
  "scripts/upgrade-airgap.sh"
  "docs/air-gapped-deployment.md"
  "docs/air-gapped-upgrade.md"
  "docs/production-compose.md"
  "docs/split-airgap-artifacts.md"
  "release-manifest.json"
  "checksums.txt"
)

[[ -d "$artifact_dir" ]] || fail "artifact directory not found: $artifact_dir"
artifact_dir="$(cd "$artifact_dir" && pwd)"
if [[ -n "$image_parts_dir" ]]; then
  [[ -d "$image_parts_dir" ]] || fail "image parts directory not found: $image_parts_dir"
  image_parts_dir="$(cd "$image_parts_dir" && pwd)"
fi
cd "$artifact_dir"

for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || fail "required file is missing: $file"
done
if [[ ! -f "images/tomorrowland-images.tar" && ! -f "images/README-images.txt" ]]; then
  fail "required file is missing: images/README-images.txt or images/tomorrowland-images.tar"
fi
log "Required files are present"

sha256sum -c checksums.txt
log "Checksums are valid"

for key in release_version git_commit created_at images compose_files minimum_docker_version minimum_compose_version migrations persistent_data backup_restore_script_version; do
  if ! grep -Eq "\"${key}\"[[:space:]]*:" release-manifest.json; then
    fail "release-manifest.json is missing required key: $key"
  fi
done
if ! grep -Eq '"image_bundle"[[:space:]]*:' release-manifest.json; then
  log "WARNING: release-manifest.json has no image_bundle metadata; assuming legacy embedded image bundle"
fi
log "Release manifest includes required upgrade safety keys"

if grep -Eiq '(password|secret|token|private[_-]?key)[[:space:]]*=[[:space:]]*([^#[:space:]]+)' .env.airgap.example; then
  if grep -Eiv '(changeme|change-me|replace-me|example|placeholder|<.*>|^#)' .env.airgap.example | grep -Eiq '(password|secret|token|private[_-]?key)[[:space:]]*='; then
    fail ".env.airgap.example appears to contain a non-placeholder secret value"
  fi
fi
log "Packaged environment template contains no obvious non-placeholder secrets"

tmp_dir="$(mktemp -d)"
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT

if ! docker compose --env-file .env.airgap.example -f docker-compose.airgap.yml config > "$tmp_dir/compose.rendered.yml"; then
  fail "docker compose config failed for docker-compose.airgap.yml"
fi
log "docker compose config passed"

if grep -Eq '^[[:space:]]+build:' "$tmp_dir/compose.rendered.yml" docker-compose.airgap.yml; then
  fail "air-gapped compose configuration must not contain build steps"
fi
log "No build steps are present in the air-gapped compose configuration"

if ! docker compose --env-file .env.airgap.example -f docker-compose.airgap.yml config --images > "$tmp_dir/compose-images.txt"; then
  fail "could not list compose images"
fi

if [[ ! -s "$tmp_dir/compose-images.txt" ]]; then
  fail "compose image list is empty"
fi

resolve_split_parts() {
  local candidate_dir
  local -a dirs=()
  if [[ -n "$image_parts_dir" ]]; then
    dirs+=("$image_parts_dir")
  fi
  dirs+=("$(dirname "$artifact_dir")" "$artifact_dir")

  for candidate_dir in "${dirs[@]}"; do
    [[ -d "$candidate_dir" ]] || continue
    mapfile -t split_parts < <(find "$candidate_dir" -maxdepth 1 -type f -name 'tomorrowland-images-*.tar.part-*' | sort)
    if [[ ${#split_parts[@]} -gt 0 ]]; then
      split_parts_dir="$candidate_dir"
      return 0
    fi
  done
  return 1
}

split_parts=()
split_parts_dir=""
image_tar_for_validation=""
if [[ -f "images/tomorrowland-images.tar" ]]; then
  image_tar_for_validation="$artifact_dir/images/tomorrowland-images.tar"
  log "Using embedded image bundle: images/tomorrowland-images.tar"
elif resolve_split_parts; then
  log "Using split image bundle from $split_parts_dir"
  parts_checksum="$(find "$split_parts_dir" -maxdepth 1 -type f -name 'tomorrowland-images-*.tar.parts.sha256' | sort | head -n 1 || true)"
  [[ -n "$parts_checksum" ]] || fail "split image parts found but tomorrowland-images-*.tar.parts.sha256 is missing"
  log "Validating split image part checksums with $(basename "$parts_checksum")"
  (cd "$split_parts_dir" && sha256sum -c "$(basename "$parts_checksum")")

  expected_index=0
  for part in "${split_parts[@]}"; do
    suffix="${part##*.tar.part-}"
    expected_suffix="$(printf '%03d' "$expected_index")"
    [[ "$suffix" == "$expected_suffix" ]] || fail "split image parts are not contiguous: expected suffix $expected_suffix but found $suffix in $part"
    expected_index=$((expected_index + 1))
  done
  log "Split image parts are contiguous (${#split_parts[@]} part(s))"

  image_tar_for_validation="$tmp_dir/tomorrowland-images.tar"
  log "Reconstructing split image bundle for metadata validation"
  cat "${split_parts[@]}" > "$image_tar_for_validation"
else
  fail "image bundle not found. Expected images/tomorrowland-images.tar or split parts tomorrowland-images-*.tar.part-* beside the artifact"
fi

if ! tar -tf "$image_tar_for_validation" >/dev/null; then
  fail "image bundle is not a readable tar archive: $image_tar_for_validation"
fi
if ! tar -xOf "$image_tar_for_validation" manifest.json > "$tmp_dir/manifest.json"; then
  fail "image bundle does not contain Docker manifest.json"
fi

missing=0
while IFS= read -r image; do
  [[ -n "$image" ]] || continue
  if grep -Fq "\"$image\"" "$tmp_dir/manifest.json"; then
    printf '  bundled  %s\n' "$image"
  else
    printf '  missing  %s\n' "$image" >&2
    missing=1
  fi
done < "$tmp_dir/compose-images.txt"
[[ "$missing" -eq 0 ]] || fail "one or more compose images are missing from the offline image bundle"
log "Every compose image is present in the offline image bundle"

# ------------------------------------------------------------------
# MCP adapter validation (#564)
# ------------------------------------------------------------------

# Verify the mcp-server service is defined in the air-gapped Compose file.
if ! grep -q 'mcp-server:' docker-compose.airgap.yml; then
  fail "air-gapped compose configuration must include mcp-server service"
fi

# Verify the mcp-server service uses the backend image (no separate build required).
if grep -A 20 '^  mcp-server:' "$tmp_dir/compose.rendered.yml" | grep -q 'build:'; then
  fail "mcp-server service must use an image reference, not a build step"
fi

# Verify mcp-server port binding restricts to localhost.
if ! grep -q '127.0.0.1:.*8001' docker-compose.airgap.yml; then
  log "WARNING: mcp-server port may not be bound to 127.0.0.1; air-gapped deployments should bind to localhost only"
fi

log "MCP adapter service is present and properly configured in the air-gapped Compose file"

if [[ "$load_images" -eq 1 ]]; then
  log "Loading image bundle into local Docker daemon for verification"
  docker load -i "$image_tar_for_validation"
  while IFS= read -r image; do
    [[ -n "$image" ]] || continue
    docker image inspect "$image" >/dev/null || fail "loaded Docker daemon is missing image: $image"
  done < "$tmp_dir/compose-images.txt"
  log "Loaded images are available locally"
fi

log "Air-gapped artifact validation passed"
