# Phase 09a: NiFi Event Integration

## Goal

Implement full NiFi event-driven ingestion beyond the registered connector stub and wire up
the Kafka consumer path needed for production event flow.

## Phase Placement

Branch: `developer/phase-09a-nifi-integration`

Status: Planned (follows Phase 08f production hardening).

## Current Baseline

- `NiFiConnector` is registered in the source connector registry.
- The connector stub is accepted by the connector abstraction but does not yet process live
  NiFi flow-file events.
- Kafka is present in the Compose runtime; consumer wiring is not implemented.
- All ingestion paths route through the existing pipeline worker and DLQ.

## Dependencies

- Phase 03d pipeline worker and DLQ.
- Phase 04 admin operations and ingestion source admin APIs.
- Phase 08a Compose runtime with Kafka service healthy.
- Existing source-grant permission model.

## Scope

### NiFi Connector Implementation

- Receive flow-file event payloads from NiFi (HTTP callback or Kafka topic depending on
  confirmed deployment topology).
- Parse NiFi-supplied metadata: filename, MIME type, source path, content bytes.
- Normalize into the standard `IngestedDocument` contract used by all connectors.
- Route normalized documents through the existing fast worker pipeline.
- On connector failure, route the event to the DLQ with a `nifi_event_failure` reason.

### Kafka Consumer Wiring

- Implement a consumer for the configured ingestion topic.
- Decode event envelopes; dispatch to the connector pipeline by event type.
- Commit offsets only after the pipeline worker completes or DLQ-routes the document.
- Support bounded exponential backoff on transient consumer errors.
- Expose consumer state through the existing admin health surface when available.

### Permission Model

- NiFi-ingested documents must be tied to an admin-configured ingestion source.
- Access must be governed by the source-grant model exactly as folder-ingested documents.
- No NiFi-specific permission bypass.

## Decision Gates

- Confirm NiFi event delivery mechanism: HTTP callback vs. Kafka producer.
- Confirm acceptable message envelope format.

## Implementation Notes

- Prefer deterministic NiFi and Kafka consumer tests over live service dependencies.
- Use the existing `ExtractorRegistry` for MIME-based content extraction of NiFi payloads.
- Do not introduce a long-running worker container in this phase; reuse the synchronous
  pipeline worker path.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_nifi_connector.py -q
pytest tests/unit/test_kafka_consumer.py -q
pytest tests/integration/test_nifi_integration.py -q
```

## Acceptance Criteria

- NiFi flow-file events are normalized and processed through the standard pipeline.
- Connector failures are routed to the DLQ without crashing the consumer.
- NiFi documents are subject to the source-grant permission model.
- Kafka consumer offsets are committed only after successful processing or DLQ routing.
- Existing connector tests remain green.
- All tests pass with deterministic fixtures; no live NiFi or Kafka service required.
