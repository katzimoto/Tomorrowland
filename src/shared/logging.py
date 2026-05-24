from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from shared.correlation import get_correlation_id
from shared.request_context import get_request_id

# Allowlisted structured extra fields surfaced in the JSON payload.
# Only fields in this tuple are forwarded — all other extras are silently dropped
# so that future log() call sites cannot accidentally leak sensitive values by
# passing arbitrary keyword arguments.
_ALLOWED_EXTRA_FIELDS: tuple[str, ...] = ("component", "outcome", "operation_id")


class JsonFormatter(logging.Formatter):
    """Format log records as structured JSON with a consistent schema.

    Mandatory fields
    ----------------
    ``timestamp``   RFC 3339 UTC (millisecond precision).
    ``level``       Lowercase level name: debug / info / warning / error / critical.
    ``logger``      Python logger name.
    ``message``     Human-readable event summary; must not contain secrets or
                    document content (caller responsibility).

    Context fields
    --------------
    ``request_id``    From the Phase 10a request-context variable; present on
                      HTTP-triggered records only.
    ``correlation_id`` Fallback correlation token (preserved for backward compat).

    Optional structured extras  (pass via ``logging.info(..., extra={...})``)
    -------------------------------------------------------------------------
    ``component``    Subsystem: api / auth / connector / admin / pipeline /
                     search / translation / intelligence.
    ``outcome``      success / failure / skipped / retry / dlq.
    ``operation_id`` Connector sync or validation workflow identifier.

    Error fields
    ------------
    ``error_type``  Exception *class name only* (not the message).  Present only
                    when ``exc_info`` is attached to the record.
    ``exc_info``    Full formatted traceback for debugging.

    Security guarantees
    -------------------
    Only fields in ``_ALLOWED_EXTRA_FIELDS`` are surfaced from ``extra``.
    Arbitrary extra keys (e.g. ``password``, ``jwt``, ``token``) are silently
    dropped so log call sites cannot accidentally leak credentials.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Request / correlation IDs
        request_id = get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        payload["correlation_id"] = getattr(record, "correlation_id", None) or get_correlation_id()

        # Allowlisted structured extras from logger.info(..., extra={...})
        for field in _ALLOWED_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = str(value)[:500]

        # Exception: error_type is class name only; full traceback in exc_info
        if record.exc_info and record.exc_info[1] is not None:
            payload["error_type"] = type(record.exc_info[1]).__name__
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, sort_keys=True)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Configure root logging for services that do not need custom handlers."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)


def log_extra(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return logging extra values with a correlation ID."""
    values = dict(extra or {})
    values.setdefault("correlation_id", get_correlation_id())
    return values
