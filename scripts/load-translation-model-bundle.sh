#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[load-translation-model-bundle] %s\n' "$*"; }
fail() { printf '[load-translation-model-bundle] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/load-translation-model-bundle.sh --bundle <path> [--target-dir <dir>]

Load a Tomorrowland translation model bundle into the target directory.

Validates bundle checksums and manifest integrity, then copies model files
to the target directory. For Docker-deployed providers, this script can
copy files into the libretranslate_data Docker volume.

Options:
  --bundle <path>        Path to the .tar.gz bundle archive (required).
  --target-dir <dir>     Directory to extract models into.
                         Default: ./models/translation
  --docker-volume <name> Docker volume name to copy models into
                         (e.g. tomorrowland_libretranslate_data).
                         When set, models are copied into the volume
                         rather than a local directory.
  --help                 Show this help.
USAGE
}

bundle=""
target_dir=""
docker_volume=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)
      bundle="${2:-}"; shift 2 ;;
    --target-dir)
      target_dir="${2:-}"; shift 2 ;;
    --docker-volume)
      docker_volume="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      fail "unknown argument: $1" ;;
  esac
done

[[ -n "$bundle" ]] || fail "--bundle is required"
[[ -f "$bundle" ]] || fail "bundle archive not found: $bundle"

command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

if [[ -n "$docker_volume" ]]; then
  command -v docker >/dev/null 2>&1 || fail "docker is required when --docker-volume is set"
fi

tmp_dir="$(mktemp -d)"
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 1. Verify outer checksum (if available)
# ---------------------------------------------------------------------------
checksum_path="${bundle}.sha256"
if [[ -f "$checksum_path" ]]; then
  log "Validating bundle checksum"
  (
    cd "$(dirname "$bundle")"
    sha256sum -c "$(basename "$checksum_path")"
  )
else
  log "WARNING: bundle checksum file not found: ${checksum_path}"
fi

# ---------------------------------------------------------------------------
# 2. Extract bundle
# ---------------------------------------------------------------------------
log "Extracting bundle: ${bundle}"
tar -xzf "$bundle" -C "$tmp_dir"
mapfile -t roots < <(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | sort)
[[ "${#roots[@]}" -eq 1 ]] || fail "bundle must contain exactly one top-level directory"
bundle_root="${roots[0]}"

# ---------------------------------------------------------------------------
# 3. Validate required bundle files
# ---------------------------------------------------------------------------
[[ -f "$bundle_root/manifest.json" ]] || fail "bundle is missing manifest.json"
[[ -f "$bundle_root/checksums.txt" ]] || fail "bundle is missing checksums.txt"
[[ -d "$bundle_root/models" ]] || fail "bundle is missing models/"

# ---------------------------------------------------------------------------
# 4. Validate internal checksums
# ---------------------------------------------------------------------------
log "Validating internal bundle checksums"
(
  cd "$bundle_root"
  sha256sum -c checksums.txt >/dev/null
)

# ---------------------------------------------------------------------------
# 5. Validate manifest structure
# ---------------------------------------------------------------------------
log "Validating manifest structure"
python3 - "$bundle_root/manifest.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

required = [
    "bundle_version",
    "tomorrowland_release",
    "created_at",
    "provider",
    "supported_languages",
    "language_pairs",
    "models_dir",
    "expected_env",
    "files",
]
missing = [k for k in required if k not in manifest]
provider = manifest.get("provider", {})
if not isinstance(provider, dict):
    missing.append("provider(must be object)")
else:
    for k in ("name", "model_family", "format"):
        if k not in provider:
            missing.append(f"provider.{k}")

files = manifest.get("files", [])
if not isinstance(files, list) or not files:
    missing.append("files(non-empty array)")

languages = manifest.get("supported_languages", [])
if not isinstance(languages, list) or not languages:
    missing.append("supported_languages(non-empty array)")

if missing:
    for key in missing:
        print(f"missing or invalid manifest field: {key}", file=sys.stderr)
    sys.exit(1)

model_family = provider.get("model_family", "")
provider_name = provider.get("name", "unknown")
version = provider.get("version") or "unknown"
print(
    f"  Provider: {provider_name} / {model_family} / {version}",
    file=sys.stderr,
)
print(f"  Languages: {len(languages)}", file=sys.stderr)
print(f"  Pairs: {len(manifest.get('language_pairs', []))}", file=sys.stderr)
print(f"  Model files: {len(files)}", file=sys.stderr)
PY

# ---------------------------------------------------------------------------
# 6. Copy model files to target
# ---------------------------------------------------------------------------
if [[ -n "$docker_volume" ]]; then
  log "Copying model files into Docker volume: ${docker_volume}"
  docker volume inspect "$docker_volume" >/dev/null 2>&1 || fail "Docker volume not found: ${docker_volume}"
  docker run --rm \
    -v "${docker_volume}:/target" \
    -v "${bundle_root}/models:/bundle-models:ro" \
    alpine:latest \
    sh -c 'mkdir -p /target/share/argos-translate/packages && cp -a /bundle-models/. /target/share/argos-translate/packages/'
  log "Models loaded into Docker volume: ${docker_volume}"
else
  target="${target_dir:-./models/translation}"
  log "Copying model files to: ${target}"
  mkdir -p "$target"
  cp -a "$bundle_root/models/." "$target/"
  log "Models loaded into: ${target}"
fi

log "Translation model bundle loaded successfully"

# Print next steps
cat <<NEXT

Next steps:
  - For Docker deployments using libretranslate:
    Restart the libretranslate service to detect the new models:
      docker compose restart libretranslate
  - Validate translation languages:
      bash scripts/validate-translation-languages.sh
NEXT
