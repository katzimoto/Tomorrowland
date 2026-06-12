#!/bin/sh
set -e
# Ensure /data is writable by appuser. Runs as root so that upgrades from
# root-only deployments (where the named volume was created with root ownership)
# are handled transparently without manual operator intervention.
chown -R appuser:appuser /data 2>/dev/null || true
exec gosu appuser "$@"
