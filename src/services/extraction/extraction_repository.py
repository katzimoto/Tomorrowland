"""Repository for document_extractions audit trail.

Follows the same SQLAlchemy Core + Connection pattern.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from shared.db import db_uuid, to_uuid


def _now() -> datetime:
    return datetime.now(UTC)


def _resolve_json(value: Any) -> Any:
    """Deserialize a JSON column from the database."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value)) if value else None
    except (json.JSONDecodeError, TypeError):
        return None


def _row_to_dict(row: sa.RowMapping) -> dict[str, Any]:
    """Convert a document_extractions row to a dict with proper UUID/JSON handling."""
    return {
        "id": str(to_uuid(row["id"])),
        "document_id": str(to_uuid(row["document_id"])),
        "parser_name": row["parser_name"],
        "parser_version": row["parser_version"],
        "duration_ms": int(row["duration_ms"]),
        "confidence": row.get("confidence"),
        "warnings": _resolve_json(row["warnings"]) or [],
        "attempts": _resolve_json(row["attempts"]) or [],
        "created_at": (
            row["created_at"].isoformat()
            if isinstance(row.get("created_at"), datetime)
            else str(row["created_at"])
            if row.get("created_at")
            else None
        ),
    }


class DocumentExtractionRepository:
    """Read and write the document_extractions audit trail."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def record(
        self,
        *,
        document_id: UUID,
        parser_name: str,
        parser_version: str,
        duration_ms: int = 0,
        confidence: float | None = None,
        warnings: list[str] | None = None,
        attempts: list[str] | None = None,
    ) -> UUID:
        """Insert a new extraction record. Returns the record UUID."""
        extraction_id = uuid4()
        now = _now()
        self._connection.execute(
            sa.text(
                """\
                INSERT INTO document_extractions (
                    id, document_id, parser_name, parser_version,
                    duration_ms, confidence, warnings, attempts, created_at
                ) VALUES (
                    :id, :document_id, :parser_name, :parser_version,
                    :duration_ms, :confidence, :warnings, :attempts, :created_at
                )
                """
            ),
            {
                "id": db_uuid(extraction_id),
                "document_id": db_uuid(document_id),
                "parser_name": parser_name,
                "parser_version": parser_version,
                "duration_ms": duration_ms,
                "confidence": confidence,
                "warnings": json.dumps(warnings or []),
                "attempts": json.dumps(attempts or []),
                "created_at": now,
            },
        )
        return extraction_id

    def get_latest(self, document_id: UUID) -> dict[str, Any] | None:
        """Return the most recent extraction record for a document, or None."""
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT * FROM document_extractions "
                    "WHERE document_id = :document_id "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"document_id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        return _row_to_dict(row) if row else None

    def list_by_document(self, document_id: UUID) -> list[dict[str, Any]]:
        """Return all extraction records for a document, newest first."""
        rows = (
            self._connection.execute(
                sa.text(
                    "SELECT * FROM document_extractions "
                    "WHERE document_id = :document_id "
                    "ORDER BY created_at DESC"
                ),
                {"document_id": db_uuid(document_id)},
            )
            .mappings()
            .all()
        )
        return [_row_to_dict(r) for r in rows]
