#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[build-translation-model-bundle] %s\n' "$*"; }
fail() { printf '[build-translation-model-bundle] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/build-translation-model-bundle.sh <version> [--provider <name>]

Build a Tomorrowland translation model bundle on a connected machine.

The bundle packages translation model files for a provider (currently Argos
via LibreTranslate) into a self-contained .tar.gz for air-gapped deployment.

Environment:
  RELEASE_DIST_DIR                  Output directory (default: dist)
  TRANSLATION_MODEL_PROVIDER        Provider name (default: argos)
  LIBRETRANSLATE_URL                LibreTranslate URL for metadata detection
                                    (default: http://localhost:5000)
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

version="${1:-}"
[[ -n "$version" ]] || fail "version argument is required"

provider="${TRANSLATION_MODEL_PROVIDER:-argos}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      [[ $# -ge 2 ]] || fail "--provider requires a name"
      provider="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

safe_version="${version//\//-}"
provider_slug="$(printf '%s' "$provider" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g')"
dist_dir="${RELEASE_DIST_DIR:-dist}"
bundle_name="tomorrowland-translation-bundle-${provider_slug}-${safe_version}"
bundle_dir="${dist_dir}/${bundle_name}"
archive_path="${dist_dir}/${bundle_name}.tar.gz"

rm -rf "$bundle_dir" "$archive_path" "${archive_path}.sha256"
mkdir -p "$bundle_dir/models"

# ---------------------------------------------------------------------------
# Provider-specific model collection
# ---------------------------------------------------------------------------

libretranslate_url="${LIBRETRANSLATE_URL:-http://localhost:5000}"

detect_provider_metadata() {
  # Query LibreTranslate /spec for provider version info.
  local spec_json
  if spec_json="$(curl -fsS --max-time 10 "${libretranslate_url}/spec")"; then
    local info_version
    info_version="$(printf '%s' "$spec_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
info = data.get('info', {})
ver = info.get('version', '')
print(ver)
")"
    if [[ -n "$info_version" ]]; then
      printf 'libretranslate-%s' "$info_version"
      return
    fi
  fi
  echo "unknown"
}

collect_language_pairs() {
  # Query LibreTranslate /languages to discover which languages are available.
  local languages_json
  if ! languages_json="$(curl -fsS --max-time 10 "${libretranslate_url}/languages")"; then
    fail "Could not reach LibreTranslate /languages at ${libretranslate_url}"
  fi
  printf '%s' "$languages_json" | python3 - "$bundle_dir" "$provider" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

bundle_dir = Path(sys.argv[1])
provider = sys.argv[2]

languages = json.load(sys.stdin)
codes = sorted({entry.get("code", "") for entry in languages if isinstance(entry, dict) and entry.get("code")})
codes = [c for c in codes if c and len(c) == 2]

# Build the full set of source→target pairs (bidirectional all→all).
# For Argos, all supported codes translate to/from every other code.
pairs = []
for src in codes:
    for tgt in codes:
        if src != tgt:
            pairs.append({"source": src, "target": tgt})

manifest_path = bundle_dir / "language_pairs.json"
manifest_path.write_text(json.dumps({
    "supported_languages": codes,
    "language_pairs": pairs,
}, indent=2) + "\n", encoding="utf-8")

# Print for bash capture
print(json.dumps({"supported_languages": codes, "pair_count": len(pairs)}))
PY
}

log "Detecting provider metadata from ${libretranslate_url}"
provider_version="$(detect_provider_metadata)"
log "Provider version: ${provider_version}"

log "Collecting language pairs"
pairs_json="$(collect_language_pairs)"
supported_languages="$(printf '%s' "$pairs_json" | python3 -c "import json,sys; print(','.join(json.load(sys.stdin)['supported_languages']))")"
pair_count="$(printf '%s' "$pairs_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['pair_count'])")"
log "Supported languages: ${supported_languages} (${pair_count} pairs)"

# ---------------------------------------------------------------------------
# Model file bundling
# ---------------------------------------------------------------------------
# For the Argos provider, model files live inside the libretranslate_data
# volume at /home/libretranslate/.local/share/argos-translate/packages.
# We export them by running a temporary container against the volume.
#
# For future providers (CTranslate2, etc.), replace this block with the
# provider-specific model collection logic.

log "Exporting Argos Translate model packages"

# Create a temporary export directory
export_dir="${bundle_dir}/models"

# Try to read models from a running libretranslate container.
# If unavailable, look for the libretranslate_data Docker volume.
container_id="$(docker ps -q -f name=libretranslate | head -n 1 || true)"
if [[ -n "$container_id" ]]; then
  log "Exporting models from running libretranslate container (${container_id})"
  docker cp "${container_id}:/home/libretranslate/.local/share/argos-translate/packages/." "${export_dir}/" || true
elif docker volume inspect tomorrowland_libretranslate_data >/dev/null 2>&1; then
  log "Exporting models from libretranslate_data Docker volume"
  docker run --rm \
    -v tomorrowland_libretranslate_data:/libretranslate_data:ro \
    -v "${export_dir}:/export" \
    alpine:latest \
    sh -c 'cp -a /libretranslate_data/share/argos-translate/packages/. /export/ || true' || true
else
  log "WARNING: could not find libretranslate container or volume; models directory will be empty"
  log "Either start the libretranslate service first, or set LIBRETRANSLATE_URL to a reachable instance"
fi

# ---------------------------------------------------------------------------
# Generate manifest
# ---------------------------------------------------------------------------

created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log "Generating manifest.json"
python3 - "$bundle_dir" "$safe_version" "$created_at" "$provider" "$provider_version" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

bundle_dir = Path(sys.argv[1])
version = sys.argv[2]
created_at = sys.argv[3]
provider = sys.argv[4]
provider_version = sys.argv[5]

# Load language pairs collected earlier
pairs_data = json.loads((bundle_dir / "language_pairs.json").read_text(encoding="utf-8"))

# Inventory model files
files = []
models_dir = bundle_dir / "models"
if models_dir.is_dir():
    for path in sorted(models_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(bundle_dir).as_posix()
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            size = path.stat().st_size
            files.append({"path": rel, "sha256": sha, "size_bytes": size})

supported_langs_str = ",".join(pairs_data["supported_languages"])

manifest = {
    "bundle_version": "1.0",
    "tomorrowland_release": version,
    "created_at": created_at,
    "provider": {
        "name": provider,
        "version": provider_version if provider_version != "unknown" else None,
        "model_family": provider,
        "format": "argos_package",
    },
    "supported_languages": pairs_data["supported_languages"],
    "language_pairs": pairs_data["language_pairs"],
    "models_dir": "models",
    "expected_env": {
        "ARGOS_CHUNK_TYPE": "MINISBD",
        "LT_LOAD_ONLY": supported_langs_str,
        "LT_UPDATE_PACKAGES": "false",
        "LT_UPDATE_MODELS": "false",
    },
    "files": files,
    "license": {
        "name": "operator verification required",
        "source_url": None,
        "attribution": None,
        "verification_status": "operator_required",
    },
}

(bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

# Clean up temporary file
(bundle_dir / "language_pairs.json").unlink(missing_ok=True)

# Write checksums.txt
checksums = []
for p in sorted(bundle_dir.glob("**/*")):
    if p.is_file() and p.name not in {"checksums.txt", "language_pairs.json"}:
        rel = p.relative_to(bundle_dir).as_posix()
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        checksums.append(f"{sha}  {rel}\n")
(bundle_dir / "checksums.txt").write_text("".join(checksums), encoding="utf-8")

# Write README
model_count = len(files)
readme = f"""# Tomorrowland translation model bundle

Bundle: `{bundle_dir.name}`
Tomorrowland release: `{version}`
Provider: `{provider}`
Provider version: `{provider_version}`
Supported languages: {supported_langs_str}
Language pairs: {pairs_data['pair_count']}
Model files: {model_count}

This bundle contains translation model files for the `{provider}` provider.
It must not contain Tomorrowland user data, application secrets, or runtime
database/search/vector volumes.

## License and source verification

The release manager/operator is responsible for verifying redistribution
approval for the exact model artifacts before publishing or transferring
this bundle. See `manifest.json` for the recorded license/source fields.
If `license.verification_status` is `operator_required`, do not treat the
license metadata as verified.

## Air-gapped loading

Transfer this `.tar.gz` and its `.sha256` file with the platform release
artifact, then run:

```bash
sha256sum -c {bundle_dir.name}.tar.gz.sha256
tar xzf {bundle_dir.name}.tar.gz
# Then follow the provider-specific load instructions.
```

## Provider format: Argos

The Argos provider models are baked into the libretranslate Docker image
via `docker/libretranslate.Dockerfile`. This bundle is supplementary —
use it to inspect model coverage or to validate models in an air-gapped
deployment.
"""
(bundle_dir / "README.md").write_text(readme, encoding="utf-8")
PY

# ---------------------------------------------------------------------------
# Create archive
# ---------------------------------------------------------------------------

log "Creating archive: ${archive_path}"
mkdir -p "$dist_dir"
tar -C "$dist_dir" -czf "$archive_path" "$bundle_name"
(
  cd "$dist_dir"
  sha256sum "${bundle_name}.tar.gz" > "${bundle_name}.tar.gz.sha256"
)

log "Translation model bundle created: ${archive_path}"
log "Archive checksum: ${archive_path}.sha256"
log "Supported languages: ${supported_languages} (${pair_count} pairs)"
