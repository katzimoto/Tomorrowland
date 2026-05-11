from __future__ import annotations

import json
import logging
import sys
from io import StringIO

from shared.correlation import clear_correlation_id, set_correlation_id
from shared.logging import JsonFormatter, configure_json_logging, log_extra


def test_json_formatter_includes_correlation_id() -> None:
    set_correlation_id("test-correlation")
    record = logging.LogRecord("tomorrowland", logging.INFO, __file__, 1, "hello", (), None)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["correlation_id"] == "test-correlation"
    assert payload["message"] == "hello"
    clear_correlation_id()


def test_log_extra_preserves_existing_values() -> None:
    set_correlation_id("from-context")

    extra = log_extra({"user_id": "u1"})

    assert extra == {"user_id": "u1", "correlation_id": "from-context"}
    clear_correlation_id()


def test_formatter_includes_exception_info() -> None:
    try:
        raise ValueError("bad")
    except ValueError:
        exc_info = sys.exc_info()
        record = logging.getLogger("tomorrowland").makeRecord(
            "tomorrowland",
            logging.ERROR,
            __file__,
            1,
            "failed",
            (),
            exc_info=exc_info,
            func=None,
            extra=None,
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: bad" in payload["exc_info"]


def test_configure_json_logging_sets_root_handler() -> None:
    stream = StringIO()
    configure_json_logging(logging.WARNING)
    handler = logging.getLogger().handlers[0]
    handler.stream = stream  # type: ignore[attr-defined]

    logging.warning("configured")

    payload = json.loads(stream.getvalue())
    assert payload["message"] == "configured"
