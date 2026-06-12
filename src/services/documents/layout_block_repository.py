"""Repository for document_layout_blocks persistence.

Follows the existing SQLAlchemy Core + Connection pattern used across all
repositories in this project.  No ORM, no SQLModel.
"""

from __future__ import annotations

import json
from typing import Any, get_args
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RowMapping

from services.documents.models import LayoutBlockRow, LayoutBlockType
from shared.db import db_now, db_resolve_json, db_uuid, to_uuid

# Derived from the canonical Literal so the two never drift.
_VALID_BLOCK_TYPES: frozenset[str] = frozenset(get_args(LayoutBlockType))

# Column list used by every read query so future schema additions don't
# accidentally widen result sets.
_COLUMNS = (
    "id, document_id, page_number, block_type, text, "
    "bbox, parser, confidence, reading_order, created_at"
)


def _row_to_model(row: RowMapping) -> LayoutBlockRow:
    """Convert a document_layout_blocks RowMapping to a LayoutBlockRow."""
    bbox_raw = db_resolve_json(row.get("bbox"))
    bbox: tuple[float, float, float, float] | None = None
    if isinstance(bbox_raw, list) and len(bbox_raw) == 4:
        bbox = (
            float(bbox_raw[0]),
            float(bbox_raw[1]),
            float(bbox_raw[2]),
            float(bbox_raw[3]),
        )
    return LayoutBlockRow(
        id=to_uuid(row["id"]),
        document_id=to_uuid(row["document_id"]),
        page_number=row.get("page_number"),
        block_type=str(row["block_type"]),  # type: ignore[arg-type]
        text=row.get("text"),
        bbox=bbox,
        parser=str(row["parser"]),
        confidence=row.get("confidence"),
        reading_order=row.get("reading_order"),
        created_at=row["created_at"],
    )


class LayoutBlockRepository:
    """CRUD for the document_layout_blocks table.

    All methods operate on a single Connection; the caller manages
    transactions.  This matches every other repository in the codebase
    (DocumentRepository, DocumentExtractionRepository, etc.).
    """

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def bulk_upsert(
        self,
        document_id: UUID,
        blocks: list[dict[str, Any]],
    ) -> int:
        """Replace all layout blocks for *document_id* with *blocks*.

        Old blocks are deleted first (CASCADE from documents.id), then
        each block in *blocks* is inserted.  Returns the number of
        blocks written.

        Each block dict must contain at minimum ``block_type`` and
        ``parser``.  Optional keys: ``page_number``, ``text``, ``bbox``
        (list of four floats), ``confidence``, ``reading_order``.
        Unrecognised keys are ignored.
        """
        # Delete existing blocks for this document.
        self._connection.execute(
            sa.text("DELETE FROM document_layout_blocks WHERE document_id = :doc_id"),
            {"doc_id": db_uuid(document_id)},
        )

        if not blocks:
            return 0

        now = db_now()
        rows: list[dict[str, Any]] = []
        for block in blocks:
            block_type = str(block["block_type"])
            if block_type not in _VALID_BLOCK_TYPES:
                raise ValueError(
                    f"Invalid block_type: {block_type!r}. "
                    f"Must be one of {sorted(_VALID_BLOCK_TYPES)}"
                )

            # json.dumps for SQLite compatibility — sa.JSON() stores
            # text on SQLite and serialised objects on PostgreSQL;
            # json.dumps works correctly on both.  db_resolve_json
            # handles deserialisation on read regardless of driver.
            bbox = block.get("bbox")
            bbox_json: str | None = None
            if bbox is not None:
                bbox_json = json.dumps(bbox)

            rows.append(
                {
                    "id": db_uuid(uuid4()),
                    "document_id": db_uuid(document_id),
                    "page_number": block.get("page_number"),
                    "block_type": block_type,
                    "text": block.get("text"),
                    "bbox": bbox_json,
                    "parser": str(block["parser"]),
                    "confidence": block.get("confidence"),
                    "reading_order": block.get("reading_order"),
                    "created_at": now,
                }
            )

        self._connection.execute(
            sa.text(
                """\
                INSERT INTO document_layout_blocks (
                    id, document_id, page_number, block_type, text,
                    bbox, parser, confidence, reading_order, created_at
                )
                VALUES (
                    :id, :document_id, :page_number, :block_type, :text,
                    :bbox, :parser, :confidence, :reading_order, :created_at
                )
                """
            ),
            rows,
        )
        return len(rows)

    def list_by_document(
        self,
        document_id: UUID,
        *,
        block_type: str | None = None,
    ) -> list[LayoutBlockRow]:
        """Return layout blocks for *document_id* ordered by ``reading_order``.

        When *block_type* is given, only blocks of that type are returned.
        """
        sql = f"SELECT {_COLUMNS} FROM document_layout_blocks WHERE document_id = :doc_id"
        params: dict[str, Any] = {"doc_id": db_uuid(document_id)}
        if block_type is not None:
            sql += " AND block_type = :block_type"
            params["block_type"] = block_type
        sql += " ORDER BY reading_order NULLS LAST, created_at"

        rows = self._connection.execute(sa.text(sql), params).mappings()
        return [_row_to_model(r) for r in rows]

    def count_by_document(self, document_id: UUID) -> int:
        """Return the number of layout blocks for *document_id*."""
        result = self._connection.execute(
            sa.text("SELECT COUNT(*) FROM document_layout_blocks WHERE document_id = :doc_id"),
            {"doc_id": db_uuid(document_id)},
        ).scalar_one()
        return int(result)

    def has_blocks(self, document_id: UUID) -> bool:
        """Return True when *document_id* has at least one layout block."""
        row = self._connection.execute(
            sa.text("SELECT 1 FROM document_layout_blocks WHERE document_id = :doc_id LIMIT 1"),
            {"doc_id": db_uuid(document_id)},
        ).scalar_one_or_none()
        return row is not None

    def page_summary(self, document_id: UUID) -> list[dict[str, Any]]:
        """Return per-page block-type counts for *document_id*.

        Useful for the API to expose a compact ``layout_blocks_summary``
        so the frontend can show page-level structure without loading
        every block.
        """
        rows = self._connection.execute(
            sa.text(
                """\
                SELECT
                    page_number,
                    block_type,
                    COUNT(*) AS cnt
                FROM document_layout_blocks
                WHERE document_id = :doc_id
                GROUP BY page_number, block_type
                ORDER BY page_number, block_type
                """
            ),
            {"doc_id": db_uuid(document_id)},
        ).mappings()
        return [
            {
                "page_number": r["page_number"],
                "block_type": r["block_type"],
                "count": int(r["cnt"]),
            }
            for r in rows
        ]

    def delete_by_document(self, document_id: UUID) -> int:
        """Delete all layout blocks for *document_id*.

        Returns the number of rows removed.
        """
        result = self._connection.execute(
            sa.text("DELETE FROM document_layout_blocks WHERE document_id = :doc_id"),
            {"doc_id": db_uuid(document_id)},
        )
        return result.rowcount
