#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/production-audit.sh [--include-dependency-audits]

Runs bounded production-hardening checks that do not start the stack.

Checks always run:
  - git diff whitespace validation
  - Docker Compose configuration rendering
  - tracked code spot check for hardcoded secret-like assignments outside tests

Optional dependency audits:
  --include-dependency-audits  Also run `uv run pip-audit` and `npm --prefix frontend audit`.
USAGE
}

INCLUDE_DEPENDENCY_AUDITS=0
for arg in "$@"; do
  case "$arg" in
    --include-dependency-audits)
      INCLUDE_DEPENDENCY_AUDITS=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log_step() {
  echo "==> $*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 127
  fi
}

require_command git
require_command docker

log_step "Checking working tree whitespace"
git diff --check

log_step "Rendering Docker Compose configuration"
docker compose config >/dev/null

log_step "Scanning tracked application code for hardcoded secret-like assignments"
SECRET_PATTERN="(password|secret|token|api_key)[[:space:]]*[:=][[:space:]]*['\"][^$<{]"
SECRET_HITS="$(git grep -n -E "$SECRET_PATTERN" -- \
  '*.py' '*.ts' '*.tsx' \
  ':(exclude)tests/**' \
  ':(exclude)frontend/src/**/*.test.ts' \
  ':(exclude)frontend/src/**/*.test.tsx' \
  ':(exclude)frontend/src/**/*.spec.ts' \
  ':(exclude)frontend/src/**/*.spec.tsx' || true)"
if [[ -n "$SECRET_HITS" ]]; then
  echo "Potential hardcoded secret-like assignments found outside test files:" >&2
  printf '%s\n' "$SECRET_HITS" | sed -E \
    "s/((password|secret|token|api_key)[[:space:]]*[:=][[:space:]]*['\"])[^'\"]*/\\1<redacted>/" >&2
  echo "Replace real values with placeholders or document accepted false positives before review." >&2
  exit 1
fi

if [[ $INCLUDE_DEPENDENCY_AUDITS -eq 1 ]]; then
  require_command uv
  require_command npm

  log_step "Running Python dependency audit"
  uv run pip-audit

  log_step "Running frontend dependency audit"
  npm --prefix frontend audit
else
  echo "==> Skipping dependency audits; pass --include-dependency-audits to run pip-audit and npm audit."
fi

log_step "Production audit checks completed successfully"
