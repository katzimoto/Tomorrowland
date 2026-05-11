#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[release-artifact] %s\n' "$*"; }
fail() { printf '[release-artifact] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/build-release-artifact.sh [version]

Build first-party Tomorrowland images, pull third-party runtime images, save an
offline Docker image bundle, and package a versioned air-gapped release archive.

Environment:
  RELEASE_DIST_DIR     Output directory for release folders and archives (default: dist)
  SKIP_DOCKER_BUILD    Set to 1 to skip docker build/pull/save for static packaging tests
  SPLIT_IMAGE_BUNDLE   Set to 0 to embed images/tomorrowland-images.tar in the archive.
                       Defaults to 1 so GitHub Release assets stay under per-file limits.
  IMAGE_PART_SIZE      Split size passed to split -b (default: 1900m)
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version="${1:-${RELEASE_VERSION:-}}"
if [[ -z "$version" ]]; then
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    version="$(git describe --tags --always --dirty 2>/dev/null || git rev-parse --short HEAD)"
  else
    version="manual"
  fi
fi
safe_version="${version//\//-}"
dist_dir="${RELEASE_DIST_DIR:-dist}"
release_name="tomorrowland-release-${safe_version}"
release_dir="${dist_dir}/${release_name}"
archive_path="${dist_dir}/${release_name}.tar.gz"
split_image_bundle="${SPLIT_IMAGE_BUNDLE:-1}"
image_part_size="${IMAGE_PART_SIZE:-1900m}"
image_parts_prefix="tomorrowland-images-${safe_version}.tar.part-"
image_parts_sha="${dist_dir}/tomorrowland-images-${safe_version}.tar.parts.sha256"

backend_version_image="tomorrowland/backend:${safe_version}"
frontend_version_image="tomorrowland/frontend:${safe_version}"
backend_airgap_image="tomorrowland/backend:airgap"
frontend_airgap_image="tomorrowland/frontend:airgap"
libretranslate_version_image="tomorrowland/libretranslate:${safe_version}"
libretranslate_airgap_image="tomorrowland/libretranslate:airgap"
third_party_images=(
  "postgres:16-alpine"
  "redpandadata/redpanda:v24.1.9"
  "docker.elastic.co/elasticsearch/elasticsearch:8.14.3"
  "qdrant/qdrant:v1.10.1"
  "ollama/ollama:latest"
)
all_images=(
  "$backend_airgap_image"
  "$frontend_airgap_image"
  "$libretranslate_airgap_image"
  "$backend_version_image"
  "$frontend_version_image"
  "$libretranslate_version_image"
  "${third_party_images[@]}"
)

required_files=(
  "docker-compose.yml"
  "docker-compose.airgap.yml"
  ".env.airgap.example"
  "scripts/tomorrowland-airgap.sh"
  "scripts/load-airgap-images.sh"
  "scripts/validate-airgap-artifact.sh"
  "scripts/load-ollama-model-bundle.sh"
  "scripts/validate-ollama-model.sh"
  "scripts/validate-translation-languages.sh"
  "scripts/preflight-upgrade-check.sh"
  "scripts/backup-airgap-data.sh"
  "scripts/restore-airgap-data.sh"
  "scripts/upgrade-airgap.sh"
  "docs/operations/air-gapped-deployment.md"
  "docs/operations/air-gapped-upgrade.md"
  "docs/operations/production-compose.md"
  "docs/operations/split-airgap-artifacts.md"
)
for file in "${required_files[@]}"; do
  [[ -f "$file" ]] || fail "required packaging input is missing: $file"
done

rm -rf "$release_dir" "$archive_path" "${archive_path}.sha256" "${dist_dir}/${image_parts_prefix}"* "$image_parts_sha"
mkdir -p "$release_dir/images" "$release_dir/scripts" "$release_dir/docs" "$dist_dir"

image_bundle_mode="embedded"
image_bundle_path="images/tomorrowland-images.tar"
tmp_image_tar=""
if [[ "$split_image_bundle" == "1" ]]; then
  image_bundle_mode="split"
  image_bundle_path="../${image_parts_prefix}*"
  tmp_image_tar="$(mktemp "${TMPDIR:-/tmp}/tomorrowland-images-${safe_version}.XXXXXX.tar")"
  cleanup_tmp_image_tar() { rm -f "$tmp_image_tar"; }
  trap cleanup_tmp_image_tar EXIT
else
  tmp_image_tar="$release_dir/images/tomorrowland-images.tar"
fi

if [[ "${SKIP_DOCKER_BUILD:-0}" != "1" ]]; then
  command -v docker >/dev/null 2>&1 || fail "docker is required unless SKIP_DOCKER_BUILD=1"
  log "Building first-party backend image: $backend_version_image and $backend_airgap_image"
  docker build -f docker/backend.Dockerfile \
    --build-arg "APP_VERSION=${version}" \
    -t "$backend_version_image" \
    -t "$backend_airgap_image" \
    .

  log "Building first-party frontend image: $frontend_version_image and $frontend_airgap_image"
  docker build -f docker/frontend.Dockerfile \
    --build-arg "APP_VERSION=${version}" \
    -t "$frontend_version_image" \
    -t "$frontend_airgap_image" \
    .

  log "Building translation image with bundled language packs: $libretranslate_version_image and $libretranslate_airgap_image"
  docker build -f docker/libretranslate.Dockerfile \
    -t "$libretranslate_version_image" \
    -t "$libretranslate_airgap_image" \
    .

  for image in "${third_party_images[@]}"; do
    log "Pulling third-party runtime image: $image"
    docker pull "$image"
  done

  log "Saving offline image bundle"
  docker save -o "$tmp_image_tar" "${all_images[@]}"
else
  log "SKIP_DOCKER_BUILD=1 set; writing placeholder image bundle for static packaging only"
  printf 'placeholder; not a docker image bundle\n' > "$tmp_image_tar"
fi

if [[ "$image_bundle_mode" == "split" ]]; then
  command -v split >/dev/null 2>&1 || fail "split is required when SPLIT_IMAGE_BUNDLE=1"
  log "Splitting offline image bundle into ${image_part_size} parts"
  split -b "$image_part_size" -d -a 3 "$tmp_image_tar" "${dist_dir}/${image_parts_prefix}"
  if ! compgen -G "${dist_dir}/${image_parts_prefix}*" >/dev/null; then
    fail "split image bundle produced no parts"
  fi
  (
    cd "$dist_dir"
    sha256sum "${image_parts_prefix}"* > "$(basename "$image_parts_sha")"
  )
  cat > "$release_dir/images/README-images.txt" <<README
The Docker image bundle for this release is distributed as split release assets.

Expected files beside the extracted release archive:

  ${image_parts_prefix}000
  ${image_parts_prefix}001
  ...
  tomorrowland-images-${safe_version}.tar.parts.sha256

Verify the parts before transfer or loading:

  sha256sum -c tomorrowland-images-${safe_version}.tar.parts.sha256

Load the images from the extracted release directory:

  bash scripts/load-airgap-images.sh .

The loader streams the ordered parts into docker load and does not require
runtime internet access.
README
else
  cat > "$release_dir/images/README-images.txt" <<README
The Docker image bundle is embedded at:

  images/tomorrowland-images.tar

Load it from the extracted release directory:

  bash scripts/load-airgap-images.sh .
README
fi

cp docker-compose.yml "$release_dir/docker-compose.yml"
cp docker-compose.airgap.yml "$release_dir/docker-compose.airgap.yml"
sed \
  -e "s/^APP_VERSION=.*/APP_VERSION=${safe_version}/" \
  -e "s|^TOMORROWLAND_BACKEND_IMAGE=.*|TOMORROWLAND_BACKEND_IMAGE=${backend_airgap_image}|" \
  -e "s|^TOMORROWLAND_FRONTEND_IMAGE=.*|TOMORROWLAND_FRONTEND_IMAGE=${frontend_airgap_image}|" \
  .env.airgap.example > "$release_dir/.env.airgap.example"
cp scripts/tomorrowland-airgap.sh "$release_dir/scripts/tomorrowland-airgap.sh"
cp scripts/load-airgap-images.sh "$release_dir/scripts/load-airgap-images.sh"
cp scripts/validate-airgap-artifact.sh "$release_dir/scripts/validate-airgap-artifact.sh"
cp scripts/load-ollama-model-bundle.sh "$release_dir/scripts/load-ollama-model-bundle.sh"
cp scripts/validate-ollama-model.sh "$release_dir/scripts/validate-ollama-model.sh"
cp scripts/validate-translation-languages.sh "$release_dir/scripts/validate-translation-languages.sh"
cp scripts/preflight-upgrade-check.sh "$release_dir/scripts/preflight-upgrade-check.sh"
cp scripts/backup-airgap-data.sh "$release_dir/scripts/backup-airgap-data.sh"
cp scripts/restore-airgap-data.sh "$release_dir/scripts/restore-airgap-data.sh"
cp scripts/upgrade-airgap.sh "$release_dir/scripts/upgrade-airgap.sh"
chmod +x "$release_dir/scripts/"*.sh
cp docs/operations/air-gapped-deployment.md "$release_dir/docs/air-gapped-deployment.md"
cp docs/operations/air-gapped-upgrade.md "$release_dir/docs/air-gapped-upgrade.md"
cp docs/operations/production-compose.md "$release_dir/docs/production-compose.md"
cp docs/operations/split-airgap-artifacts.md "$release_dir/docs/split-airgap-artifacts.md"

git_commit="unknown"
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git_commit="$(git rev-parse HEAD 2>/dev/null || printf unknown)"
fi
created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$release_dir/release-manifest.json" <<MANIFEST
{
  "release_version": "$safe_version",
  "git_commit": "$git_commit",
  "created_at": "$created_at",
  "images": [
$(printf '    "%s"' "${all_images[0]}")
$(for image in "${all_images[@]:1}"; do printf ',\n    "%s"' "$image"; done)

  ],
  "image_bundle": {
    "mode": "$image_bundle_mode",
    "path": "$image_bundle_path",
    "split_prefix": "${image_parts_prefix}",
    "split_checksum_file": "../tomorrowland-images-${safe_version}.tar.parts.sha256",
    "part_size": "$image_part_size"
  },
  "compose_files": ["docker-compose.yml", "docker-compose.airgap.yml"],
  "minimum_docker_version": "24.0",
  "minimum_compose_version": "2.20",
  "migrations": {"expected": true, "service": "migrate", "command": "alembic upgrade head"},
  "persistent_data": {
    "volumes": ["files_data", "postgres_data", "kafka_data", "elasticsearch_data", "qdrant_data", "libretranslate_data", "ollama_data"],
    "paths": ["TOMORROWLAND_FOLDER_SOURCE_HOST_PATH"]
  },
  "backup_restore_script_version": "1.0"
}
MANIFEST

{
  printf 'Tomorrowland release artifact %s\n\n' "$version"
  printf 'Quick start (run from this directory after copying and editing .env):\n\n'
  printf '  cp .env.airgap.example .env\n'
  printf '  nano .env\n'
  printf '  ./scripts/tomorrowland-airgap.sh validate --load-images\n'
  printf '  ./scripts/tomorrowland-airgap.sh up\n'
  printf '\nImage bundle layout:\n'
  if [[ "$image_bundle_mode" == "split" ]]; then
    printf 'The Docker image bundle is distributed as split assets beside this archive.\n'
    printf 'Verify and load them with the wrapper (no manual reassembly needed):\n'
    printf '  sha256sum -c tomorrowland-images-%s.tar.parts.sha256\n' "$safe_version"
    printf '  ./scripts/tomorrowland-airgap.sh load-images\n'
    printf '\nSplit part files (required, beside the platform archive):\n'
    printf '  %s000, %s001, ...\n' "$image_parts_prefix" "$image_parts_prefix"
    printf '  tomorrowland-images-%s.tar.parts.sha256\n' "$safe_version"
  else
    printf '  images/tomorrowland-images.tar (embedded in this archive)\n'
    printf '  ./scripts/tomorrowland-airgap.sh load-images\n'
  fi
  printf '\nImages included in the offline Docker image bundle:\n'
  printf -- '- %s\n' "${all_images[@]}"
  printf '\nUpgrade existing deployment (run from the existing deployment directory):\n'
  printf '  ./scripts/tomorrowland-airgap.sh upgrade --artifact-dir ../%s\n' "$release_name"
  printf '\nOther wrapper commands: validate, status, down, backup, help\n'
  printf '\nRC2 default model bundle (separate optional release asset):\n'
  printf 'tomorrowland-ollama-bundle-mistral-%s.tar.gz\n' "$safe_version"
  printf 'Missing model bundle is a warning only; platform starts without it but\n'
  printf 'offline Q&A/RAG/local intelligence is degraded until a model is loaded.\n'
  printf 'Load with: scripts/load-ollama-model-bundle.sh\n'
  printf 'Validate with: scripts/validate-ollama-model.sh\n'
  printf '\nNever run: docker compose down -v  (deletes persistent data volumes)\n'
} > "$release_dir/README-airgap.txt"

checksum_inputs=(
  docker-compose.yml
  docker-compose.airgap.yml
  .env.airgap.example
  images/README-images.txt
  scripts/tomorrowland-airgap.sh
  scripts/load-airgap-images.sh
  scripts/validate-airgap-artifact.sh
  scripts/load-ollama-model-bundle.sh
  scripts/validate-ollama-model.sh
  scripts/validate-translation-languages.sh
  scripts/preflight-upgrade-check.sh
  scripts/backup-airgap-data.sh
  scripts/restore-airgap-data.sh
  scripts/upgrade-airgap.sh
  docs/air-gapped-deployment.md
  docs/air-gapped-upgrade.md
  docs/production-compose.md
  docs/split-airgap-artifacts.md
  release-manifest.json
  README-airgap.txt
)
if [[ "$image_bundle_mode" == "embedded" ]]; then
  checksum_inputs+=(images/tomorrowland-images.tar)
fi
(
  cd "$release_dir"
  sha256sum "${checksum_inputs[@]}" > checksums.txt
)

log "Creating archive: $archive_path"
tar -C "$dist_dir" -czf "$archive_path" "$release_name"
(
  cd "$dist_dir"
  sha256sum "${release_name}.tar.gz" > "${release_name}.tar.gz.sha256"
)

log "Release artifact created: $archive_path"
log "Archive checksum: ${archive_path}.sha256"
if [[ "$image_bundle_mode" == "split" ]]; then
  log "Image bundle parts: ${dist_dir}/${image_parts_prefix}*"
  log "Image bundle part checksums: $image_parts_sha"
fi
