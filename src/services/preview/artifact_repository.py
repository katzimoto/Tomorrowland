"""CRUD for the document_preview_artifacts table."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

from shared.db import db_now, db_resolve_json, db_uuid, to_uuid

_TERMINAL_STATUSES = {"ready", "partial", "failed"}


@dataclass(frozen=True)
class PreviewArtifactRow:
    """Row model for document_preview_artifacts."""

    id: UUID
    document_id: UUID
    content_sha256: str
    renderer: str
    status: str
    manifest: dict[str, Any] | None
    files: dict[str, str] | None
    error_category: str | None
    error_detail: str | None


class PreviewArtifactRepository:
    """DB access for preview render status and manifests."""

    def __init__(self, connection: sa.Connection) -> None:
        self._connection = connection

    def get(self, document_id: UUID, content_sha256: str) -> PreviewArtifactRow | None:
        row = (
            self._connection.execute(
                sa.text(
                    """
                SELECT id, document_id, content_sha256, renderer, status,
                       manifest, files, error_category, error_detail
                FROM document_preview_artifacts
                WHERE document_id = :document_id AND content_sha256 = :sha
                """
                ),
                {"document_id": db_uuid(document_id), "sha": content_sha256},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        manifest = db_resolve_json(row["manifest"])
        files = db_resolve_json(row["files"])
        return PreviewArtifactRow(
            id=to_uuid(row["id"]),
            document_id=to_uuid(row["document_id"]),
            content_sha256=str(row["content_sha256"]),
            renderer=str(row["renderer"]),
            status=str(row["status"]),
            manifest=manifest if isinstance(manifest, dict) else None,
            files=files if isinstance(files, dict) else None,
            error_category=row["error_category"],
            error_detail=row["error_detail"],
        )

    def create_pending(
        self, document_id: UUID, content_sha256: str, renderer: str
    ) -> PreviewArtifactRow:
        """Insert a pending row; on conflict return the existing row."""
        now = db_now()
        try:
            with self._connection.begin_nested():
                self._connection.execute(
                    sa.text(
                        """
                        INSERT INTO document_preview_artifacts
                            (id, document_id, content_sha256, renderer, status,
                             created_at, updated_at)
                        VALUES
                            (:id, :document_id, :sha, :renderer, 'pending',
                             :now, :now)
                        """
                    ),
                    {
                        "id": db_uuid(uuid4()),
                        "document_id": db_uuid(document_id),
                        "sha": content_sha256,
                        "renderer": renderer,
                        "now": now,
                    },
                )
        except sa.exc.IntegrityError:
            pass  # concurrent first view — the existing row wins
        row = self.get(document_id, content_sha256)
        assert row is not None  # just inserted or conflicted with an existing row
        return row

    def mark_running(self, document_id: UUID, content_sha256: str) -> None:
        self._update_status(document_id, content_sha256, status="running")

    def mark_rendered(
        self,
        document_id: UUID,
        content_sha256: str,
        *,
        status: str,
        manifest: dict[str, Any],
        files: dict[str, str],
    ) -> None:
        """Persist a completed render (ready or partial)."""
        if status not in ("ready", "partial"):
            raise ValueError(f"mark_rendered expects ready|partial, got {status!r}")
        self._connection.execute(
            sa.text(
                """
                UPDATE document_preview_artifacts
                SET status = :status, manifest = :manifest, files = :files,
                    error_category = NULL, error_detail = NULL, updated_at = :now
                WHERE document_id = :document_id AND content_sha256 = :sha
                """
            ),
            {
                "status": status,
                "manifest": json.dumps(manifest),
                "files": json.dumps(files),
                "now": db_now(),
                "document_id": db_uuid(document_id),
                "sha": content_sha256,
            },
        )

    def mark_failed(
        self,
        document_id: UUID,
        content_sha256: str,
        *,
        error_category: str,
        error_detail: str | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        """Persist a terminal failure — never auto-retried."""
        self._connection.execute(
            sa.text(
                """
                UPDATE document_preview_artifacts
                SET status = 'failed', error_category = :category,
                    error_detail = :detail, manifest = :manifest, updated_at = :now
                WHERE document_id = :document_id AND content_sha256 = :sha
                """
            ),
            {
                "category": error_category[:100],
                "detail": (error_detail or "")[:500] or None,
                "manifest": json.dumps(manifest) if manifest is not None else None,
                "now": db_now(),
                "document_id": db_uuid(document_id),
                "sha": content_sha256,
            },
        )

    def delete(self, document_id: UUID, content_sha256: str) -> None:
        self._connection.execute(
            sa.text(
                """
                DELETE FROM document_preview_artifacts
                WHERE document_id = :document_id AND content_sha256 = :sha
                """
            ),
            {"document_id": db_uuid(document_id), "sha": content_sha256},
        )

    def list_all_keys(self) -> set[tuple[str, str]]:
        """All live ``(document_id, content_sha256)`` pairs — for orphan sweeps."""
        rows = self._connection.execute(
            sa.text("SELECT document_id, content_sha256 FROM document_preview_artifacts")
        ).all()
        return {(str(to_uuid(r[0])), str(r[1])) for r in rows}

    def is_terminal(self, row: PreviewArtifactRow) -> bool:
        return row.status in _TERMINAL_STATUSES

    def _update_status(self, document_id: UUID, content_sha256: str, *, status: str) -> None:
        self._connection.execute(
            sa.text(
                """
                UPDATE document_preview_artifacts
                SET status = :status, updated_at = :now
                WHERE document_id = :document_id AND content_sha256 = :sha
                """
            ),
            {
                "status": status,
                "now": db_now(),
                "document_id": db_uuid(document_id),
                "sha": content_sha256,
            },
        )
