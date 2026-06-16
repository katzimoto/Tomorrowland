#!/usr/bin/env bash
# scripts/dev/check-worker-images.sh
#
# Builds the backend and preview-worker images and verifies that every worker
# command referenced in docker-compose.yml can be executed through the backend
# entrypoint. This catches two failure modes:
#
#   1. A Dockerfile that reuses the backend entrypoint forces a non-root USER,
#      causing gosu to fail with "operation not permitted".
#   2. A command is referenced in Compose but missing from pyproject.toml
#      [project.scripts], causing "executable file not found in $PATH".
#
# Usage:
#   bash scripts/dev/check-worker-images.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

BACKEND_IMAGE="tomorrowland/backend:airgap"
PREVIEW_IMAGE="tomorrowland/preview-worker:airgap"

backend_workers=(
  tomorrowland-parse-worker
  tomorrowland-translate-worker
  tomorrowland-embed-worker
  tomorrowland-index-worker
  tomorrowland-intelligence-worker
  tomorrowland-alert-worker
  tomorrowland-enrich-worker
  tomorrowland-mcp-server
)

echo "==> Building worker images"
docker build -f docker/backend.Dockerfile -t "$BACKEND_IMAGE" .
docker build -f docker/preview-worker.Dockerfile --build-arg "TOMORROWLAND_BACKEND_IMAGE=$BACKEND_IMAGE" -t "$PREVIEW_IMAGE" .

echo "==> Verifying backend worker commands"
for cmd in "${backend_workers[@]}"; do
  echo "  checking: $cmd"
  docker run --rm "$BACKEND_IMAGE" sh -c "which $cmd" >/dev/null
  echo "    ok"
done

echo "==> Verifying preview-worker command"
echo "  checking: tomorrowland-preview-worker"
docker run --rm "$PREVIEW_IMAGE" sh -c "which tomorrowland-preview-worker" >/dev/null
echo "    ok"

echo "==> All worker entrypoints verified"
