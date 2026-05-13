from __future__ import annotations

import json
import logging
from io import StringIO

from shared.correlation import clear_correlation_id, set_correlation_id
from shared.logging import JsonFormatter, configure_json_logging, log_extra
from shared.request_context import reset_request_id, set_request_id


def test_json_formatter_emits_base_schema() -> None:
    set_correlation_id("test-correlation")
    record = logging.LogRecord("tomorrowland", logging.INFO, __file__, 1, "hello", (), None)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["timestamp"].endswith("Z")
    assert payload["level"] == "info"
    assert payload["logger"] == "tomorrowland"
    assert payload["message"] == "hello"
    assert payload["component"] == "application"
    assert payload["outcome"] == "unknown"
    assert payload["correlation_id"] == "test-correlation"
    clear_correlation_id()


def test_json_formatter_includes_request_id_when_bound() -> None:
    token = set_request_id("request-123")
    try:
        record = logging.LogRecord("tomorrowland", logging.INFO, __file__, 1, "hello", (), None)

        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["request_id"] == "request-123"


def test_json_formatter_emits_only_safe_structured_fields() -> None:
    record = logging.getLogger("tomorrowland").makeRecord(
        "tomorrowland",
        logging.INFO,
        __file__,
        1,
        "completed",
        (),
        exc_info=None,
        func=None,
        extra={
            "component": "api",
            "outcome": "success",
            "route": "/documents/{doc_id}",
            "method": "GET",
            "status_code": 200,
            "duration_ms": 12.5,
            "raw_request_body": "must not be logged",
            "password": "must not be logged",
            "nested": {"must": "drop"},
        },
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["component"] == "api"
    assert payload["outcome"] == "success"
    assert payload["route"] == "/documents/{doc_id}"
    assert payload["method"] == "GET"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5
    assert "raw_request_body" not in payload
    assert "password" not in payload
    assert "nested" not in payload


def test_json_formatter_falls_back_for_unsafe_required_fields() -> None:
    record = logging.getLogger("tomorrowland").makeRecord(
        "tomorrowland",
        logging.INFO,
        __file__,
        1,
        "completed",
        (),
        exc_info=None,
        func=None,
        extra={"component": {"unsafe": "drop"}, "outcome": ["drop"]},
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["component"] == "application"
    assert payload["outcome"] == "unknown"


def test_log_extra_drops_unapproved_values() -> None:
    set_correlation_id("from-context")

    extra = log_extra(
        {
            "route": "/search",
            "status_code": 500,
            "user_id": "u1",
            "raw_request_body": "must not be logged",
            "indexed": 1,
            "metadata": {"unsafe": "drop"},
        }
    )

    assert extra == {
        "correlation_id": "from-context",
        "route": "/search",
        "status_code": 500,
        "indexed": 1,
    }
    clear_correlation_id()


def test_formatter_records_exception_type_without_traceback_payload() -> None:
    try:
        raise ValueError("unsafe detail")
    except ValueError as exc:
        record = logging.getLogger("tomorrowland").makeRecord(
            "tomorrowland",
            logging.ERROR,
            __file__,
            1,
            "failed",
            (),
            exc_info=(type(exc), exc, exc.__traceback__),
            func=None,
            extra=None,
        )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["error_type"] == "ValueError"
    assert "exc_info" not in payload
    assert "unsafe detail" not in json.dumps(payload)


def test_configure_json_logging_adds_root_handler_without_removing_existing_handlers() -> None:
    stream = StringIO()
    sentinel = logging.NullHandler()
    root = logging.getLogger()
    original_level = root.level
    handler: logging.Handler | None = None
    try:
        root.addHandler(sentinel)
        handler = configure_json_logging(logging.WARNING)
        handler.stream = stream  # type: ignore[attr-defined]

        logging.warning("configured")

        payload = json.loads(stream.getvalue())
        assert payload["message"] == "configured"
        assert sentinel in root.handlers
        assert handler in root.handlers
    finally:
        if handler is not None:
            root.removeHandler(handler)
        root.removeHandler(sentinel)
        root.setLevel(original_level)
