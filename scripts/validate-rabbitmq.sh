#!/usr/bin/env bash
set -euo pipefail

RABBITMQ_MGMT_URL="${RABBITMQ_MGMT_URL:-http://localhost:15672}"
RABBITMQ_USER="${RABBITMQ_USER:-tomorrowland}"
RABBITMQ_PASS="${RABBITMQ_PASS:-changeme}"

STAGES=("parse" "translate" "embed" "index" "intelligence" "alert")
EXPECTED_QUEUES=()
for stage in "${STAGES[@]}"; do
    EXPECTED_QUEUES+=("document.${stage}.requested")
    EXPECTED_QUEUES+=("document.${stage}.dead")
    EXPECTED_QUEUES+=("document.${stage}.retry")
done

echo "Validating RabbitMQ topology at ${RABBITMQ_MGMT_URL} ..."

# Check broker is reachable
if ! curl -sf -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${RABBITMQ_MGMT_URL}/api/overview" > /dev/null 2>&1; then
    echo "FAIL: RabbitMQ management API unreachable at ${RABBITMQ_MGMT_URL}"
    exit 1
fi

actual=$(curl -sf -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${RABBITMQ_MGMT_URL}/api/queues" 2>&1)
if [[ -z "$actual" ]]; then
    echo "FAIL: could not retrieve queue list"
    exit 1
fi

missing=0
for queue in "${EXPECTED_QUEUES[@]}"; do
    if echo "$actual" | grep -q "\"name\":\"${queue}\""; then
        echo "PASS: ${queue}"
    else
        echo "FAIL: ${queue} — missing"
        missing=1
    fi
done

if [[ $missing -eq 0 ]]; then
    echo ""
    echo "All ${#EXPECTED_QUEUES[@]} queues present — topology is valid."
    exit 0
else
    echo ""
    echo "Topology validation FAILED — $missing queue(s) missing."
    exit 1
fi
