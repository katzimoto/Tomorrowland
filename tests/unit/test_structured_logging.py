"""Unit tests for structured JSON logging — Issue #63 / Phase 10e.

Covers:
- JSON validity and mandatory field presence
- Timestamp is RFC 3339 UTC
- level is lowercase
- request_id flows from Phase 10a context variable
- error_type is class name only (never the exception message)
- Allowlisted extras (component, outcome, operation_id) are surfaced
- Arbitrary extras (password, token, …) are silently dropped
- No credential-like field names appear as JSON keys
- OpenTelemetry start_span is a no-op when the package is absent
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime

import pytest

from shared.logging import JsonFormatter
from shared.request_context import reset_request_id, set_request_id

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    message: str = "test message",
    level: int = logging.INFO,
    exc_info: object = None,
    **extra: object,
) -> logging.LogRecord:
    """Build a LogRecord with optional level, exc_info, and extra attributes."""
    record = logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,  # type: ignore[arg-type]
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _format(record: logging.LogRecord) -> dict:  # type: ignore[type-arg]
    """Format a record with JsonFormatter and parse the result."""
    raw = JsonFormatter().format(record)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# JSON validity and mandatory fields
# ---------------------------------------------------------------------------


def test_output_is_valid_json() -> None:
    raw = JsonFormatter().format(_make_record())
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_mandatory_fields_present() -> None:
    payload = _format(_make_record("hello"))
    assert payload["message"] == "hello"
    assert "level" in payload
    assert "logger" in payload
    assert "timestamp" in payload


def test_message_matches_log_call() -> None:
    payload = _format(_make_record("pipeline stage complete"))
    assert payload["message"] == "pipeline stage complete"


def test_logger_name_preserved() -> None:
    record = _make_record()
    record.name = "services.pipeline.worker"
    payload = _format(record)
    assert payload["logger"] == "services.pipeline.worker"


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------


def test_timestamp_ends_with_z() -> None:
    payload = _format(_make_record())
    ts = payload["timestamp"]
    assert ts.endswith("Z"), f"timestamp {ts!r} must end with Z (UTC)"


def test_timestamp_is_parseable_iso8601() -> None:
    payload = _format(_make_record())
    ts = payload["timestamp"]
    # Must round-trip through ISO 8601 parsing
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt).total_seconds() == 0  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Level
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level,expected",
    [
        (logging.DEBUG, "debug"),
        (logging.INFO, "info"),
        (logging.WARNING, "warning"),
        (logging.ERROR, "error"),
        (logging.CRITICAL, "critical"),
    ],
)
def test_level_is_lowercase(level: int, expected: str) -> None:
    payload = _format(_make_record(level=level))
    assert payload["level"] == expected


# ---------------------------------------------------------------------------
# request_id from Phase 10a context
# ---------------------------------------------------------------------------


def test_request_id_present_when_context_set() -> None:
    token = set_request_id("req-test-abc")
    try:
        payload = _format(_make_record())
        assert payload.get("request_id") == "req-test-abc"
    finally:
        reset_request_id(token)


def test_request_id_absent_when_context_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shared.logging.get_request_id", lambda: None)
    payload = _format(_make_record())
    assert "request_id" not in payload


# ---------------------------------------------------------------------------
# error_type — class name only, never the exception message
# ---------------------------------------------------------------------------


def test_error_type_is_class_name() -> None:
    try:
        raise ValueError("contains sensitive: query=top secret content")
    except ValueError:
        exc = sys.exc_info()

    payload = _format(_make_record("operation failed", logging.ERROR, exc_info=exc))

    assert payload["error_type"] == "ValueError"


def test_error_type_does_not_contain_exception_message() -> None:
    try:
        raise RuntimeError("password=hunter2 token=abc123")
    except RuntimeError:
        exc = sys.exc_info()

    payload = _format(_make_record("failed", logging.ERROR, exc_info=exc))

    # error_type must be class name only
    assert payload["error_type"] == "RuntimeError"
    assert "hunter2" not in payload["error_type"]
    assert "token" not in payload["error_type"]


def test_exc_info_included_when_exception_present() -> None:
    try:
        raise KeyError("missing")
    except KeyError:
        exc = sys.exc_info()

    payload = _format(_make_record("lookup failed", logging.ERROR, exc_info=exc))

    assert "exc_info" in payload
    assert "error_type" in payload


def test_no_error_type_when_no_exception() -> None:
    payload = _format(_make_record("normal event"))
    assert "error_type" not in payload
    assert "exc_info" not in payload


# ---------------------------------------------------------------------------
# Allowlisted structured extras
# ---------------------------------------------------------------------------


def test_component_field_surfaced() -> None:
    payload = _format(_make_record(component="pipeline"))
    assert payload.get("component") == "pipeline"


def test_outcome_field_surfaced() -> None:
    payload = _format(_make_record(outcome="success"))
    assert payload.get("outcome") == "success"


def test_operation_id_field_surfaced() -> None:
    payload = _format(_make_record(operation_id="sync-op-42"))
    assert payload.get("operation_id") == "sync-op-42"


def test_all_allowed_extras_together() -> None:
    payload = _format(
        _make_record(
            "connector sync",
            component="connector",
            outcome="failure",
            operation_id="op-99",
        )
    )
    assert payload["component"] == "connector"
    assert payload["outcome"] == "failure"
    assert payload["operation_id"] == "op-99"


# ---------------------------------------------------------------------------
# Non-allowlisted / sensitive extras are silently dropped
# ---------------------------------------------------------------------------


def test_unlisted_extra_not_surfaced() -> None:
    payload = _format(_make_record(arbitrary_field="some value"))
    assert "arbitrary_field" not in payload


def test_credential_extras_not_surfaced() -> None:
    payload = _format(
        _make_record(
            password="hunter2",  # type: ignore[call-arg]
            jwt="eyJhbGc...",  # type: ignore[call-arg]
            token="secret-token",  # type: ignore[call-arg]
            api_key="sk-1234",  # type: ignore[call-arg]
        )
    )
    assert "password" not in payload
    assert "jwt" not in payload
    assert "token" not in payload
    assert "api_key" not in payload


# ---------------------------------------------------------------------------
# No credential field names appear as JSON keys
# ---------------------------------------------------------------------------


def test_no_sensitive_field_names_in_output() -> None:
    payload = _format(_make_record("auth event"))
    for sensitive_key in ("password", "secret", "jwt", "api_key", "credential"):
        assert sensitive_key not in payload, (
            f"Sensitive field name {sensitive_key!r} must not appear in log payload"
        )


# ---------------------------------------------------------------------------
# Monitoring-view fields: all required fields are queryable
# ---------------------------------------------------------------------------


def test_monitoring_queryable_fields() -> None:
    """All fields the monitoring view needs for search/filter are present."""
    token = set_request_id("req-monitor-1")
    try:
        payload = _format(
            _make_record(
                "connector sync completed",
                component="connector",
                outcome="success",
                operation_id="op-monitor-1",
            )
        )
        # Filter by level
        assert "level" in payload
        # Filter by component
        assert payload["component"] == "connector"
        # Filter by outcome
        assert payload["outcome"] == "success"
        # Filter by operation_id (for connector sync/failure UI linkage)
        assert payload["operation_id"] == "op-monitor-1"
        # Search by request_id
        assert payload["request_id"] == "req-monitor-1"
        # Filter by time range
        assert "timestamp" in payload
    finally:
        reset_request_id(token)


# ---------------------------------------------------------------------------
# OpenTelemetry no-op hook
# ---------------------------------------------------------------------------


def test_start_span_noop_without_otel_package() -> None:
    """start_span must execute the body even when opentelemetry is not installed."""
    from shared.tracing import start_span

    executed: list[bool] = []
    with start_span("test.operation", document_id="doc-1"):
        executed.append(True)

    assert executed == [True], "start_span body must always execute"


def test_start_span_accepts_attributes() -> None:
    """start_span must not raise when given keyword attributes."""
    from shared.tracing import start_span

    with start_span(
        "pipeline.embed",
        document_id="doc-abc",
        source_id="src-xyz",
        stage="embed",
    ):
        pass  # Must not raise
