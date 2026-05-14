from __future__ import annotations

import json
import logging

import pytest

from shared.logging import SAFE_LOG_FIELDS, JsonFormatter, log_extra
from shared.request_context import set_request_id


@pytest.fixture(autouse=True)
def _reset_request_id() -> None:
    set_request_id(None)


def _make_record(
    msg: str = "test",
    level: int = logging.INFO,
    logger_name: str = "test.logger",
    extra: dict | None = None,
) -> logging.LogRecord:
    record = logging.LogRecord(logger_name, level, "test.py", 1, msg, (), None)
    if extra:
        for key, value in extra.items():
            setattr(record, key, value)
    return record


def _format(record: logging.LogRecord) -> dict:
    formatter = JsonFormatter()
    return json.loads(formatter.format(record))


class TestJsonFormatter:
    def test_parses_as_json(self) -> None:
        record = _make_record()
        result = _format(record)
        assert isinstance(result, dict)

    def test_required_base_fields_exist(self) -> None:
        record = _make_record("hello")
        result = _format(record)
        assert "timestamp" in result
        assert "level" in result
        assert "logger" in result
        assert "message" in result
        assert "component" in result
        assert "outcome" in result
        assert result["message"] == "hello"
        assert result["level"] == "info"
        assert result["logger"] == "test.logger"

    def test_includes_request_id_when_set(self) -> None:
        set_request_id("req-123")
        record = _make_record()
        result = _format(record)
        assert result["request_id"] == "req-123"

    def test_omits_request_id_when_not_set(self) -> None:
        record = _make_record()
        result = _format(record)
        assert "request_id" not in result

    def test_approved_extra_fields_are_emitted(self) -> None:
        extra = log_extra({"component": "api", "outcome": "success", "status_code": 200})
        record = _make_record("test", extra=extra)
        result = _format(record)
        assert result["component"] == "api"
        assert result["outcome"] == "success"
        assert result["status_code"] == 200

    def test_unknown_extra_fields_are_dropped(self) -> None:
        extra = log_extra({"component": "api", "secret_token": "s3cr3t"})
        record = _make_record("test", extra=extra)
        result = _format(record)
        assert result["component"] == "api"
        assert "secret_token" not in result

    def test_unsafe_field_types_are_dropped(self) -> None:
        extra = log_extra({"component": "api", "nested": {"key": "val"}})
        record = _make_record("test", extra=extra)
        result = _format(record)
        assert "nested" not in result

    def test_error_type_from_exc_info(self) -> None:
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            record = _make_record("error", level=logging.ERROR)
            record.exc_info = logging.ERROR  # wrong type, let's use proper
            # Actually set exc_info properly
            import sys

            record.exc_info = sys.exc_info()
        result = _format(record)
        assert result["error_type"] == "RuntimeError"

    def test_error_type_does_not_include_exception_message(self) -> None:
        try:
            raise ValueError("user credentials: secret-token")
        except ValueError:
            record = _make_record("error", level=logging.ERROR)
            import sys

            record.exc_info = sys.exc_info()
        result = _format(record)
        assert result["error_type"] == "ValueError"
        assert "secret-token" not in json.dumps(result)

    def test_component_defaults_to_application(self) -> None:
        record = _make_record()
        result = _format(record)
        assert result["component"] == "application"

    def test_outcome_defaults_to_unknown(self) -> None:
        record = _make_record()
        result = _format(record)
        assert result["outcome"] == "unknown"

    def test_level_renders_as_lowercase_string(self) -> None:
        record = _make_record("warn", level=logging.WARNING)
        result = _format(record)
        assert result["level"] == "warning"

    def test_timestamp_is_rfc3339(self) -> None:
        record = _make_record()
        result = _format(record)
        ts = result["timestamp"]
        assert ts.endswith("Z")
        assert "T" in ts

    def test_safe_field_list_is_frozen(self) -> None:
        assert isinstance(SAFE_LOG_FIELDS, frozenset)


class TestLogExtra:
    def test_only_safe_fields_pass_through(self) -> None:
        result = log_extra({"component": "api", "password": "hunter2"})
        assert result.get("component") == "api"
        assert "password" not in result

    def test_unsafe_numeric_values_are_kept(self) -> None:
        result = log_extra({"status_code": 200, "duration_ms": 45})
        assert result["status_code"] == 200
        assert result["duration_ms"] == 45

    def test_none_values_are_dropped(self) -> None:
        result = log_extra({"component": None})
        assert "component" not in result

    def test_unsafe_types_are_dropped(self) -> None:
        result = log_extra({"method": ["GET", "POST"]})
        assert "method" not in result

    def test_empty_extra_returns_correlation_id_only(self) -> None:
        result = log_extra()
        assert isinstance(result, dict)
        assert "correlation_id" in result
