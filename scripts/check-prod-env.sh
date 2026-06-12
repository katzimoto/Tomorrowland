#!/usr/bin/env bash
# Preflight check: refuse to start with known-insecure default secret values.
# Exits non-zero and prints the offending keys if any dangerous defaults are
# found. Intended to be called by tomorrowland-airgap.sh before `docker compose up`.
set -euo pipefail

env_file="${1:-.env}"

fail() { printf '[check-prod-env] ERROR: %s\n' "$*" >&2; }
warn() { printf '[check-prod-env] WARNING: %s\n' "$*" >&2; }

if [[ ! -f "$env_file" ]]; then
  fail "env file not found: $env_file"
  exit 1
fi

errors=0

# Read a key's value from the env file (strips quotes, ignores comments).
env_val() {
  local key="$1"
  awk -F= -v k="$key" '
    /^[[:space:]]*#/ { next }
    $1 == k {
      sub(/^[^=]*=/, "")
      gsub(/^[[:space:]]+|[[:space:]]+$/, "")
      gsub(/^"|"$/, "")
      gsub(/^'"'"'|'"'"'$/, "")
      print
      exit
    }
  ' "$env_file"
}

check_key() {
  local key="$1"
  local val
  val="$(env_val "$key")"
  [[ -z "$val" ]] && return  # not set — compose default will trigger its own error
  if [[ "$val" == *"change-me-"* || "$val" == "changeme" || "$val" == "dev-meilisearch-master-key" ]]; then
    fail "$key contains an unset placeholder value ('$val'). Replace it before starting."
    errors=$((errors + 1))
  fi
}

# Keys that must not be left at their example/default placeholder values.
check_key POSTGRES_PASSWORD
check_key POSTGRES_URL
check_key JWT_SECRET
check_key MEILISEARCH_MASTER_KEY
check_key RABBITMQ_PASS
check_key RABBITMQ_URL

# CREDENTIAL_STORE_KEY must be non-empty when set in the env file.
csk="$(env_val CREDENTIAL_STORE_KEY)"
if [[ -n "$(grep -E '^[[:space:]]*CREDENTIAL_STORE_KEY[[:space:]]*=' "$env_file" || true)" && -z "$csk" ]]; then
  fail "CREDENTIAL_STORE_KEY is set but empty. Provide a secret key or remove the line to use the default."
  errors=$((errors + 1))
fi

if [[ $errors -gt 0 ]]; then
  fail "$errors secret(s) are still at placeholder values. Edit $env_file and retry."
  exit 1
fi

# Soft warning: the bootstrap admin password cannot be verified from the env
# file (it lives in the database), but operators frequently forget to change it.
warn "Remember to change the default admin@local.com password after first login."

printf '[check-prod-env] Preflight checks passed.\n'
