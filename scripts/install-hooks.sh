#!/bin/sh
# Install the Tomorrowland pre-commit hook

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK_SRC="$SCRIPT_DIR/pre-commit"
HOOK_DST="$REPO_ROOT/.git/hooks/pre-commit"

cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"

echo "Pre-commit hook installed to $HOOK_DST"
echo "Runs: ruff check, ruff format, mypy (tests run in CI)"
