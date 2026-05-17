from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException

from shared.db import to_uuid
from shared.metrics import current_metrics, safe_label_value

_SENSITIVE_CONFIG_KEYS = frozenset(
    {
        "api_token",
        "password",
        "token",
        "secret",
        "client_secret",
        "api_key",
        "private_key",
    }
)


def _fmt_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value.isoformat())


def _translation_score(quality: str | None) -> float:
    if quality == "high":
        return 1.0
    if quality == "fast":
        return 0.5
    return 0.0


def _parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


def _config_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _source_config(value: Any) -> dict[str, Any]:
    try:
        parsed = _parse_json(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_source_error(message: str, source_row: Any | None = None) -> str:
    sanitized = message or "Source operation failed"
    if source_row is not None:
        config = _source_config(source_row.get("config"))
        for key, value in config.items():
            if key.lower() in _SENSITIVE_CONFIG_KEYS and value not in (None, ""):
                sanitized = sanitized.replace(str(value), "[redacted]")
    sanitized = re.sub(r"//([^:/\s]+):([^@/\s]+)@", r"//[redacted]:[redacted]@", sanitized)
    return sanitized


def _classify_connection_error(
    exc: Exception, connector_type: str, source_row: Any | None = None
) -> tuple[
    Literal["ok", "unreachable", "auth_failed", "permission_denied", "config_invalid"],
    str,
]:
    message = str(exc).lower()
    if connector_type in ("smb", "folder"):
        if "does not exist" in message or "not found" in message or "unreachable" in message:
            return ("unreachable", _sanitize_source_error(str(exc), source_row))
        if "permission" in message or "access denied" in message:
            return ("permission_denied", _sanitize_source_error(str(exc), source_row))
    if connector_type in ("confluence", "jira"):
        if "401" in message or "unauthorized" in message or "auth" in message:
            return ("auth_failed", _sanitize_source_error(str(exc), source_row))
        if "403" in message or "forbidden" in message:
            return ("permission_denied", _sanitize_source_error(str(exc), source_row))
        if "connection" in message or "timeout" in message or "refused" in message:
            return ("unreachable", _sanitize_source_error(str(exc), source_row))
    if "requires" in message or "missing" in message or "invalid" in message:
        return ("config_invalid", _sanitize_source_error(str(exc), source_row))
    return ("config_invalid", _sanitize_source_error(str(exc), source_row))


def _record_source_sync_state(
    connection: sa.Connection,
    source_id: UUID,
    *,
    status: str,
    indexed: int = 0,
    skipped: int = 0,
    failed: int = 0,
    error: str | None = None,
) -> None:
    connection.execute(
        sa.text("""
            UPDATE ingestion_sources
            SET last_sync_status = :status,
                last_sync_indexed = :indexed,
                last_sync_skipped = :skipped,
                last_sync_failed = :failed,
                last_sync_error = :error,
                last_sync_at = :synced_at,
                updated_at = :synced_at
            WHERE id = :id
            """),
        {
            "id": source_id.hex,
            "status": status,
            "indexed": indexed,
            "skipped": skipped,
            "failed": failed,
            "error": error,
            "synced_at": datetime.now(UTC),
        },
    )


def _audit_log(
    connection: sa.Connection,
    user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    metrics = current_metrics()
    if metrics is not None:
        metrics.admin_actions_total.labels(
            safe_label_value(action), safe_label_value(resource_type)
        ).inc()
    connection.execute(
        sa.text("""
            INSERT INTO audit_log (id, user_id, action, resource_type, resource_id, details)
            VALUES (:id, :user_id, :action, :resource_type, :resource_id, :details)
            """),
        {
            "id": uuid4().hex,
            "user_id": user_id.hex if user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": json.dumps(details or {}),
        },
    )


def _subscription_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(to_uuid(row["id"])),
        "user_id": str(to_uuid(row["user_id"])),
        "name": row["name"],
        "query": row["query"],
        "similarity_threshold": row["similarity_threshold"],
        "enabled": bool(row["enabled"]),
        "unread_count": int(row.get("unread_count") or 0),
        "last_notified": _fmt_dt(row["last_notified"]),
        "created_at": _fmt_dt(row["created_at"]),
        "updated_at": _fmt_dt(row["updated_at"]),
    }


def _notification_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(to_uuid(row["id"])),
        "subscription_id": str(to_uuid(row["subscription_id"])),
        "subscription_name": row["subscription_name"],
        "subscription_query": row["subscription_query"],
        "document_id": str(to_uuid(row["document_id"])),
        "doc_title": row["doc_title"],
        "similarity": row["similarity"],
        "read": bool(row["read"]),
        "created_at": _fmt_dt(row["created_at"]),
    }


def require_subscriptions_enabled(connection: sa.Connection, settings: Any) -> None:
    """Raise 404 when subscriptions are disabled."""
    if not settings.feature_subscriptions:
        raise HTTPException(status_code=404, detail="Subscriptions are disabled")
    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": "feature.subscriptions"},
        )
        .mappings()
        .first()
    )
    if row and not _config_bool(row["value"], default=True):
        raise HTTPException(status_code=404, detail="Subscriptions are disabled")


def require_related_docs_enabled(connection: sa.Connection, settings: Any) -> None:
    """Raise 404 when related documents are disabled."""
    if not settings.feature_related_docs:
        raise HTTPException(status_code=404, detail="Related documents are disabled")
    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": "feature.related_docs"},
        )
        .mappings()
        .first()
    )
    if row and not _config_bool(row["value"], default=True):
        raise HTTPException(status_code=404, detail="Related documents are disabled")


def require_expertise_enabled(connection: sa.Connection, settings: Any) -> None:
    """Raise 404 when expertise map is disabled."""
    if not settings.feature_expertise_map:
        raise HTTPException(status_code=404, detail="Expertise map is disabled")
    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": "feature.expertise_map"},
        )
        .mappings()
        .first()
    )
    if row and not _config_bool(row["value"], default=True):
        raise HTTPException(status_code=404, detail="Expertise map is disabled")


def related_docs_limit(connection: sa.Connection) -> int:
    """Read related document limit from runtime config."""
    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": "search.related_docs_limit"},
        )
        .mappings()
        .first()
    )
    if row is None:
        return 5
    return int(row["value"])


def default_alert_threshold(connection: sa.Connection) -> float:
    """Read the default alert similarity threshold from runtime config."""
    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": "alerts.similarity_threshold"},
        )
        .mappings()
        .first()
    )
    if row is None:
        return 0.75
    return float(row["value"])


def alerts_check_on_ingest(connection: sa.Connection) -> bool:
    """Return whether ingest-time alert matching is enabled."""
    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": "alerts.check_on_ingest"},
        )
        .mappings()
        .first()
    )
    return _config_bool(row["value"], default=True) if row else True
