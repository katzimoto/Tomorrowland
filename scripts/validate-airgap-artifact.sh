#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[validate-airgap-artifact] %s\n' "$*"; }
fail() { printf '[validate-airgap-artifact] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/validate-airgap-artifact.sh [--load-images] [--image-parts-dir DIR] [--model-bundle PATH] [artifact-directory]

Validate an extracted Tomorrowland air-gapped release artifact.
Checks required files, checksums, compose rendering, forbidden build steps, and
that every image referenced by docker-compose.airgap.yml exists in the offline
Docker image bundle. With --load-images, also docker-loads the bundle and verifies
image presence in the local Docker daemon.

The image bundle can be either:
  - images/tomorrowland-images.tar inside the artifact directory; or
  - split parts named tomorrowland-images-<version>.tar.part-* beside the artifact.

If --model-bundle is provided, TOMORROWLAND_OLLAMA_MODEL_BUNDLE is set, or a
tomorrowland-ollama-bundle-*.tar.gz archive is found next to the artifact, this
script validates the model bundle manifest and checksums. If no model bundle is
present, validation warns but does not fail the base platform artifact.
USAGE
}

load_images=0
model_bundle="${TOMORROWLAND_OLLAMA_MODEL_BUNDLE:-}"
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
    --model-bundle)
      model_bundle="${2:-}"
      [[ -n "$model_bundle" ]] || fail "--model-bundle requires a path"
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
  "scripts/load-ollama-model-bundle.sh"
  "scripts/validate-ollama-model.sh"
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

if [[ -n "$model_bundle" ]]; then
  [[ -f "$model_bundle" ]] || fail "model bundle archive not found: $model_bundle"
  model_bundle="$(cd "$(dirname "$model_bundle")" && pwd)/$(basename "$model_bundle")"
fi
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

validate_model_bundle() {
  local bundle_path="$1"
  [[ -f "$bundle_path" ]] || fail "model bundle archive not found: $bundle_path"

  local checksum_path="${bundle_path}.sha256"
  if [[ -f "$checksum_path" ]]; then
    log "Validating model bundle outer checksum: $checksum_path"
    (cd "$(dirname "$bundle_path")" && sha256sum -c "$(basename "$checksum_path")" >/dev/null)
  else
    log "WARNING: model bundle checksum file is missing: $checksum_path"
  fi

  local bundle_tmp
  bundle_tmp="$(mktemp -d)"
  tar -xzf "$bundle_path" -C "$bundle_tmp"
  mapfile -t bundle_roots < <(find "$bundle_tmp" -mindepth 1 -maxdepth 1 -type d | sort)
  [[ "${#bundle_roots[@]}" -eq 1 ]] || fail "model bundle must contain exactly one top-level directory"
  local bundle_root="${bundle_roots[0]}"

  [[ -f "$bundle_root/model-manifest.json" ]] || fail "model bundle is missing model-manifest.json"
  [[ -f "$bundle_root/checksums.txt" ]] || fail "model bundle is missing checksums.txt"
  [[ -d "$bundle_root/models" ]] || fail "model bundle is missing models/"

  (cd "$bundle_root" && sha256sum -c checksums.txt >/dev/null)

  python3 - "$bundle_root/model-manifest.json" <<'PY_VALIDATE_MODEL_MANIFEST'
from __future__ import annotations
import json
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = [
    "bundle_version",
    "tomorrowland_release",
    "created_at",
    "requested_model",
    "resolved_model",
    "resolved_digest",
    "ollama_runtime_image",
    "ollama_runtime_version",
    "expected_env",
    "model_source",
    "license",
    "files",
]
missing = [key for key in required if key not in manifest or manifest[key] in (None, "")]
license_data = manifest.get("license", {})
license_required = ["name", "source_url", "attribution", "verification_status"]
missing_license = [f"license.{key}" for key in license_required if key not in license_data]
if manifest.get("resolved_digest") == "unknown":
    missing.append("resolved_digest(non-unknown)")
if license_data.get("verification_status") not in {"verified", "operator_required"}:
    missing_license.append("license.verification_status(valid)")
if not isinstance(manifest.get("files"), list) or not manifest["files"]:
    missing.append("files(non-empty)")
if missing or missing_license:
    for key in missing + missing_license:
        print(f"missing or invalid model manifest field: {key}", file=sys.stderr)
    sys.exit(1)
PY_VALIDATE_MODEL_MANIFEST
  rm -rf "$bundle_tmp"
  log "Ollama model bundle validation passed: $bundle_path"
}

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

if [[ -z "$model_bundle" ]]; then
  search_parent="$(cd "$artifact_dir/.." && pwd)"
  mapfile -t found_bundles < <(find "$artifact_dir" "$search_parent" -maxdepth 1 -type f -name 'tomorrowland-ollama-bundle-*.tar.gz' 2>/dev/null | sort -u)
  if [[ "${#found_bundles[@]}" -gt 0 ]]; then
    model_bundle="${found_bundles[0]}"
  fi
fi

if [[ -n "$model_bundle" ]]; then
  validate_model_bundle "$model_bundle"
else
  log "WARNING: no Ollama model bundle found; base platform artifact remains valid, but local Q&A/RAG is degraded until a model bundle is loaded"
fi

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
