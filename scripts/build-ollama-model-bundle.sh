#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[build-ollama-model-bundle] %s\n' "$*"; }
fail() { printf '[build-ollama-model-bundle] ERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
Usage: scripts/build-ollama-model-bundle.sh <version>

Build a Tomorrowland Ollama model bundle on a connected machine.

Environment:
  OLLAMA_MODEL                         Model to pull (default: mistral)
  OLLAMA_RUNTIME_IMAGE                 Ollama image to use (default: ollama/ollama:latest)
  RELEASE_DIST_DIR                     Output directory (default: dist)
  OLLAMA_MODEL_LICENSE_NAME            Verified/operator-approved license name
  OLLAMA_MODEL_LICENSE_SOURCE_URL      License/source URL for the bundled model
  OLLAMA_MODEL_ATTRIBUTION             Attribution text for the bundled model
  OLLAMA_MODEL_SOURCE                  Model source registry (default: registry.ollama.ai)
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

version="${1:-}"
[[ -n "$version" ]] || fail "version argument is required"

command -v docker >/dev/null 2>&1 || fail "docker is required to build an Ollama model bundle"
command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

docker info >/dev/null 2>&1 || fail "Docker daemon is not reachable"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

model="${OLLAMA_MODEL:-mistral}"
runtime_image="${OLLAMA_RUNTIME_IMAGE:-ollama/ollama:latest}"
dist_dir="${RELEASE_DIST_DIR:-dist}"
safe_version="${version//\//-}"
model_slug="$(printf '%s' "$model" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g')"
[[ -n "$model_slug" ]] || fail "could not derive shell-safe model slug from OLLAMA_MODEL=$model"

bundle_name="tomorrowland-ollama-bundle-${model_slug}-${safe_version}"
bundle_dir="${dist_dir}/${bundle_name}"
archive_path="${dist_dir}/${bundle_name}.tar.gz"
volume_name="tomorrowland_ollama_bundle_${model_slug}_${safe_version}_$$"
container_name="tomorrowland-ollama-bundle-${model_slug}-$$"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  docker volume rm "$volume_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

rm -rf "$bundle_dir" "$archive_path" "${archive_path}.sha256"
mkdir -p "$bundle_dir"

log "Pulling Ollama runtime image: $runtime_image"
docker pull "$runtime_image" >/dev/null

log "Creating temporary Ollama volume: $volume_name"
docker volume create "$volume_name" >/dev/null

log "Starting temporary Ollama runtime without GPU requirements"
docker run -d --name "$container_name" \
  -e OLLAMA_MODELS=/root/.ollama/models \
  -v "$volume_name:/root/.ollama" \
  "$runtime_image" serve >/dev/null

log "Waiting for Ollama API"
for _ in {1..60}; do
  if docker exec "$container_name" ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$container_name" ollama list >/dev/null 2>&1 || fail "Ollama did not become ready"

log "Pulling model: $model"
if ! docker exec "$container_name" ollama pull "$model"; then
  fail "ollama pull failed for model: $model"
fi

log "Collecting model identity metadata"
docker exec "$container_name" ollama list > "$bundle_dir/ollama-list.txt"
if docker exec "$container_name" ollama show --json "$model" > "$bundle_dir/ollama-show.json"; then
  :
else
  printf '{}\n' > "$bundle_dir/ollama-show.json"
fi
runtime_version="$(docker exec "$container_name" ollama --version 2>/dev/null | awk '{print $NF}' || true)"
[[ -n "$runtime_version" ]] || runtime_version="unknown"

log "Copying Ollama models directory into bundle staging area"
mkdir -p "$bundle_dir/models"
docker cp "$container_name:/root/.ollama/models/." "$bundle_dir/models/"

python3 - "$bundle_dir" "$version" "$model" "$runtime_image" "$runtime_version" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

bundle_dir = Path(sys.argv[1])
version = sys.argv[2]
requested_model = sys.argv[3]
runtime_image = sys.argv[4]
runtime_version = sys.argv[5]

model_with_tag = requested_model if ":" in requested_model.split("/")[-1] else f"{requested_model}:latest"
resolved_model = model_with_tag
resolved_digest = "unknown"
list_path = bundle_dir / "ollama-list.txt"
if list_path.exists():
    for line in list_path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0] in {requested_model, model_with_tag}:
            resolved_model = parts[0]
            resolved_digest = parts[1]
            break

show_path = bundle_dir / "ollama-show.json"
show_data: dict[str, object] = {}
try:
    show_data = json.loads(show_path.read_text(encoding="utf-8"))
except Exception:
    show_data = {}
for key in ("digest", "model_info", "details"):
    value = show_data.get(key)
    if isinstance(value, str) and value:
        resolved_digest = value
        break

manifest_files = sorted((bundle_dir / "models" / "manifests").glob("**/*"))
manifest_files = [path for path in manifest_files if path.is_file()]
if resolved_digest == "unknown" and manifest_files:
    digest = hashlib.sha256(manifest_files[0].read_bytes()).hexdigest()
    resolved_digest = f"sha256:{digest}"

files = []
for path in sorted((bundle_dir / "models").glob("**/*")):
    if not path.is_file():
        continue
    rel = path.relative_to(bundle_dir).as_posix()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    files.append({"path": rel, "sha256": sha})

license_name = os.environ.get("OLLAMA_MODEL_LICENSE_NAME", "").strip()
license_source = os.environ.get("OLLAMA_MODEL_LICENSE_SOURCE_URL", "").strip()
attribution = os.environ.get("OLLAMA_MODEL_ATTRIBUTION", "").strip()
verified = bool(license_name and license_source)
license_data = {
    "name": license_name or "operator verification required",
    "source_url": license_source or None,
    "attribution": attribution or None,
    "verification_status": "verified" if verified else "operator_required",
}

manifest = {
    "bundle_version": "1.0",
    "tomorrowland_release": version,
    "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "requested_model": requested_model,
    "resolved_model": resolved_model,
    "resolved_digest": resolved_digest,
    "ollama_runtime_image": runtime_image,
    "ollama_runtime_version": runtime_version,
    "expected_env": {"OLLAMA_MODEL": requested_model},
    "model_source": os.environ.get("OLLAMA_MODEL_SOURCE", "registry.ollama.ai"),
    "license": license_data,
    "files": files,
}
(bundle_dir / "model-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

readme = f"""# Tomorrowland Ollama model bundle

Bundle: `{bundle_dir.name}`
Tomorrowland release: `{version}`
Requested model: `{requested_model}`
Resolved model: `{resolved_model}`
Resolved digest: `{resolved_digest}`
Ollama runtime image: `{runtime_image}`
Ollama runtime version: `{runtime_version}`

This bundle contains only the Ollama `models/` directory copied from a temporary Docker volume created for this build. It must not contain Tomorrowland user data, application secrets, or runtime database/search/vector volumes.

## License and source verification

The release manager/operator is responsible for verifying redistribution approval for the exact model artifact before publishing or transferring this bundle. See `model-manifest.json` for the recorded license/source fields. If `license.verification_status` is `operator_required`, do not treat the license metadata as verified.

## Air-gapped loading

Transfer this `.tar.gz` and its `.sha256` file with the platform release artifact, then run:

```bash
sha256sum -c {bundle_dir.name}.tar.gz.sha256
bash scripts/load-ollama-model-bundle.sh --bundle {bundle_dir.name}.tar.gz --compose-file docker-compose.airgap.yml --env-file .env
bash scripts/validate-ollama-model.sh --smoke-test
```
"""
(bundle_dir / "README-ollama-bundle.md").write_text(readme, encoding="utf-8")

checksum_paths = [p for p in sorted(bundle_dir.glob("**/*")) if p.is_file() and p.name != "checksums.txt"]
with (bundle_dir / "checksums.txt").open("w", encoding="utf-8") as handle:
    for path in checksum_paths:
        rel = path.relative_to(bundle_dir).as_posix()
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        handle.write(f"{sha}  {rel}\n")
PY

rm -f "$bundle_dir/ollama-list.txt" "$bundle_dir/ollama-show.json"
# Regenerate checksums after removing transient metadata files from the final bundle.
python3 - "$bundle_dir" <<'PY'
from __future__ import annotations
import hashlib
import sys
from pathlib import Path
bundle_dir = Path(sys.argv[1])
with (bundle_dir / "checksums.txt").open("w", encoding="utf-8") as handle:
    for path in sorted(bundle_dir.glob("**/*")):
        if path.is_file() and path.name != "checksums.txt":
            rel = path.relative_to(bundle_dir).as_posix()
            handle.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}\n")
PY

log "Creating archive: $archive_path"
mkdir -p "$dist_dir"
tar -C "$dist_dir" -czf "$archive_path" "$bundle_name"
(
  cd "$dist_dir"
  sha256sum "${bundle_name}.tar.gz" > "${bundle_name}.tar.gz.sha256"
)

log "Model bundle created: $archive_path"
log "Archive checksum: ${archive_path}.sha256"
log "Review model-manifest.json license.verification_status before publishing."
