#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[load-airgap-images] %s\n' "$*"; }
fail() { printf '[load-airgap-images] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/load-airgap-images.sh [--image-parts-dir DIR] [artifact-directory]

Load Tomorrowland offline Docker images from either:
  - images/tomorrowland-images.tar inside the extracted release archive; or
  - split image parts named tomorrowland-images-<version>.tar.part-* beside it.

Run this on the air-gapped host after extracting the release archive.

Options:
  --image-parts-dir DIR  Directory containing split tomorrowland-images-*.tar.part-* files.
                         Defaults to the artifact directory's parent, then artifact dir.
USAGE
}

image_parts_dir=""
artifact_dir=""
while [[ $# -gt 0 ]]; do
  case "$1" in
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
      if [[ -n "$artifact_dir" ]]; then
        fail "unexpected extra argument: $1"
      fi
      artifact_dir="$1"
      shift
      ;;
  esac
done

artifact_dir="${artifact_dir:-$(pwd)}"
command -v docker >/dev/null 2>&1 || fail "docker is required to load images"
[[ -d "$artifact_dir" ]] || fail "artifact directory not found: $artifact_dir"

artifact_dir="$(cd "$artifact_dir" && pwd)"
if [[ -n "$image_parts_dir" ]]; then
  [[ -d "$image_parts_dir" ]] || fail "image parts directory not found: $image_parts_dir"
  image_parts_dir="$(cd "$image_parts_dir" && pwd)"
fi

image_tar="${artifact_dir}/images/tomorrowland-images.tar"
tmp_files=()
cleanup() {
  if [[ ${#tmp_files[@]} -gt 0 ]]; then
    rm -f "${tmp_files[@]}"
  fi
}
trap cleanup EXIT

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
if [[ -f "$image_tar" ]]; then
  log "Loading Docker images from embedded bundle: $image_tar"
  docker load -i "$image_tar"
elif resolve_split_parts; then
  parts_checksum="$(find "$split_parts_dir" -maxdepth 1 -type f -name 'tomorrowland-images-*.tar.parts.sha256' | sort | head -n 1 || true)"
  if [[ -n "$parts_checksum" ]]; then
    log "Validating split image part checksums with $(basename "$parts_checksum")"
    (cd "$split_parts_dir" && sha256sum -c "$(basename "$parts_checksum")")
  else
    log "WARNING: no tomorrowland-images-*.tar.parts.sha256 file found next to split image parts"
  fi

  log "Loading Docker images from ${#split_parts[@]} split image part(s)"
  for part in "${split_parts[@]}"; do
    printf '  part  %s\n' "$part"
  done
  cat "${split_parts[@]}" | docker load
else
  fail "image bundle not found. Expected $image_tar or split parts tomorrowland-images-*.tar.part-* beside the artifact"
fi
log "Docker image load complete"

if [[ -f "${artifact_dir}/docker-compose.airgap.yml" ]]; then
  log "Images required by docker-compose.airgap.yml:"
  images_file="$(mktemp)"
  err_file="$(mktemp)"
  tmp_files+=("$images_file" "$err_file")
  if docker compose --env-file "${artifact_dir}/.env.airgap.example" \
      -f "${artifact_dir}/docker-compose.airgap.yml" config --images >"$images_file" 2>"$err_file"; then
    while IFS= read -r image; do
      [[ -n "$image" ]] || continue
      if docker image inspect "$image" >/dev/null 2>&1; then
        printf '  ok  %s\n' "$image"
      else
        printf '  missing after load  %s\n' "$image"
      fi
    done < "$images_file"
  else
    log "Could not render compose image list; run validate-airgap-artifact.sh for details"
  fi
fi
