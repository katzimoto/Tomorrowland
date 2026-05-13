from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from shared.correlation import get_correlation_id
from shared.request_context import get_request_id

SAFE_LOG_FIELDS = frozenset(
    {
        "event",
        "component",
        "outcome",
        "route",
        "method",
        "status_code",
        "duration_ms",
        "error_type",
        "reason",
        "auth_provider",
        "operation_id",
        "source_id",
        "source_type",
        "validation_status",
        "failure_category",
        "indexed",
        "skipped",
        "failed",
        "discovered",
        "action",
        "resource_type",
        "resource_id",
    }
)

_ALLOWED_VALUE_TYPES = (str, int, float, bool)


def _timestamp(record: logging.LogRecord) -> str:
    """Return the record creation time as an RFC3339 UTC timestamp."""
    return datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z")


def _safe_value(value: Any) -> Any:
    """Return a JSON-safe scalar value, or ``None`` when it should be dropped."""
    if value is None or isinstance(value, _ALLOWED_VALUE_TYPES):
        return value
    return None


def _safe_string(value: Any, default: str) -> str:
    """Return a safe string value for required schema fields."""
    return value if isinstance(value, str) else default


class JsonFormatter(logging.Formatter):
    """Format log records as one safe JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = get_request_id()
        correlation_id = getattr(record, "correlation_id", get_correlation_id())
        payload: dict[str, Any] = {
            "timestamp": _timestamp(record),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "component": _safe_string(getattr(record, "component", None), "application"),
            "outcome": _safe_string(getattr(record, "outcome", None), "unknown"),
            "correlation_id": correlation_id,
        }
        if request_id is not None:
            payload["request_id"] = request_id

        for field in SAFE_LOG_FIELDS:
            if field in payload:
                continue
            value = _safe_value(getattr(record, field, None))
            if value is not None:
                payload[field] = value

        if record.exc_info and "error_type" not in payload:
            exc_type = record.exc_info[0]
            if exc_type is not None:
                payload["error_type"] = exc_type.__name__

        return json.dumps(payload, sort_keys=True)


def configure_json_logging(level: int = logging.INFO) -> logging.Handler:
    """Configure root JSON logging without removing existing capture handlers."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)
    return handler


def log_extra(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return safe logging extra values with a correlation ID."""
    values: dict[str, Any] = {"correlation_id": get_correlation_id()}
    for key, value in (extra or {}).items():
        if key not in SAFE_LOG_FIELDS:
            continue
        safe_value = _safe_value(value)
        if safe_value is not None:
            values[key] = safe_value
    return values
