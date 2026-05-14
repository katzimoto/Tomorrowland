"""Document preview service with truncated snippets and view tracking."""

from __future__ import annotations

import json
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa

from services.extraction.registry import ExtractorRegistry
from shared.db import db_uuid

SNIPPET_LENGTH = 2000


def _parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value) if value else {}
    if value is None:
        return {}
    return cast("dict[str, Any]", value)


class PreviewService:
    """Generate preview snippets and track document views."""

    def __init__(
        self,
        connection: Any,
        extractor_registry: ExtractorRegistry | None = None,
    ) -> None:
        self._connection = connection
        self._extractor = extractor_registry or ExtractorRegistry()

    def get_preview(
        self,
        doc_id: UUID,
        user_id: UUID,
        translation_version_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Return preview metadata, snippet, and view count for *doc_id*.

        Also records a view by *user_id* if not already present.
        If *translation_version_id* is provided and the version is available,
        the snippet is rendered from the stored translated text.
        """

        row = (
            self._connection.execute(
                sa.text(
                    """
                    SELECT id, title, mime_type, path, translation_quality, metadata
                    FROM documents WHERE id = :id
                    """
                ),
                {"id": db_uuid(doc_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return {}

        # Record view (deduplicated by doc_id + user_id)
        self._connection.execute(
            sa.text(
                """
                INSERT INTO document_views (id, doc_id, user_id, viewed_at)
                VALUES (:id, :doc_id, :user_id, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": db_uuid(uuid4()),
                "doc_id": db_uuid(doc_id),
                "user_id": db_uuid(user_id),
            },
        )

        # Get global view count
        view_count = self._connection.execute(
            sa.text("SELECT COUNT(*) FROM document_views WHERE doc_id = :doc_id"),
            {"doc_id": db_uuid(doc_id)},
        ).scalar_one()

        # Auto-enrich: queue for high-quality translation when view threshold is crossed
        self._maybe_auto_enrich(doc_id, view_count, row["translation_quality"])

        snippet = self._generate_snippet(
            doc_id, row["path"], row["mime_type"], translation_version_id
        )

        return {
            "doc_id": str(doc_id),
            "title": row["title"],
            "mime_type": row["mime_type"],
            "translation_quality": row["translation_quality"],
            "metadata": _parse_metadata(row["metadata"]),
            "snippet": snippet,
            "view_count": view_count,
        }

    def _generate_snippet(
        self,
        doc_id: UUID,
        file_path: str | None,
        mime_type: str,
        translation_version_id: UUID | None = None,
    ) -> str:
        """Return a truncated preview snippet for a document.

        When *translation_version_id* is provided, renders that version
        only if it is ``available`` and belongs to the same document.
        When omitted, resolves the latest available translation for the
        document (ordered by highest ``version_number``). Falls back to
        the original document extraction when no available translation
        exists.
        """
        # Determine which translation version to use
        version_id = translation_version_id

        if version_id is not None:
            # Verify the requested version is available and belongs to
            # the same doc_id (prevent cross-document version leaks).
            version_row = (
                self._connection.execute(
                    sa.text(
                        """
                        SELECT dv.translated_text, dv.doc_id
                        FROM document_translation_versions dv
                        WHERE dv.id = :id AND dv.status = 'available'
                        """
                    ),
                    {"id": db_uuid(version_id)},
                )
                .mappings()
                .first()
            )
            if version_row is None or version_row["doc_id"] != db_uuid(doc_id):
                version_id = None

        if version_id is None:
            # Resolve the latest available translation for this document
            latest_row = (
                self._connection.execute(
                    sa.text(
                        """
                        SELECT id, translated_text
                        FROM document_translation_versions
                        WHERE doc_id = :doc_id AND status = 'available'
                        ORDER BY version_number DESC
                        LIMIT 1
                        """
                    ),
                    {"doc_id": db_uuid(doc_id)},
                )
                .mappings()
                .first()
            )
            if latest_row and latest_row["translated_text"]:
                version_id = latest_row["id"]

        # If we have a resolved version, render from translated text
        if version_id is not None:
            version_row = (
                self._connection.execute(
                    sa.text(
                        """
                        SELECT translated_text
                        FROM document_translation_versions
                        WHERE id = :id
                        """
                    ),
                    {"id": db_uuid(version_id)},
                )
                .mappings()
                .first()
            )
            if version_row and version_row["translated_text"]:
                text: str = version_row["translated_text"]
                return text[:SNIPPET_LENGTH]

        # Fall back to original document extraction
        if file_path is None:
            return ""

        path = Path(file_path)
        if not path.exists():
            return ""

        # Archives: list filenames
        if mime_type in {
            "application/zip",
            "application/x-zip-compressed",
            "application/x-tar",
            "application/gzip",
        }:
            return self._archive_snippet(path)

        # Extract text using registry
        text = self._extractor.extract(path, mime_type)

        # HTML: sanitize
        if mime_type in {"text/html", "application/xhtml+xml"}:
            return self._sanitize_html(text)[:SNIPPET_LENGTH]

        # Plain text: truncate
        return text[:SNIPPET_LENGTH]

    def _maybe_auto_enrich(
        self,
        doc_id: UUID,
        view_count: int,
        current_quality: str | None,
    ) -> None:
        """Queue document for enrichment if view threshold is crossed.

        Creates a translation version record for auditability.
        """
        if current_quality in ("high", "pending_high"):
            return

        threshold_row = (
            self._connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = 'auto_enrich.threshold'"),
            )
            .mappings()
            .first()
        )
        threshold = threshold_row["value"] if threshold_row else 5
        if isinstance(threshold, str):
            threshold = int(threshold)

        if view_count < threshold:
            return

        # Check if a pending/running version already exists
        existing = self._connection.execute(
            sa.text(
                """
                    SELECT id FROM document_translation_versions
                    WHERE doc_id = :doc_id
                      AND request_type = 'auto_enrich'
                      AND status IN ('pending', 'running')
                    LIMIT 1
                    """
            ),
            {"doc_id": db_uuid(doc_id)},
        ).scalar_one_or_none()
        if existing:
            return

        # Create auto_enrich version
        next_number = self._connection.execute(
            sa.text(
                """
                    SELECT COALESCE(MAX(version_number), 0) + 1
                    FROM document_translation_versions
                    WHERE doc_id = :doc_id
                    """
            ),
            {"doc_id": db_uuid(doc_id)},
        ).scalar_one()

        self._connection.execute(
            sa.text(
                """
                INSERT INTO document_translation_versions (
                    id, doc_id, version_number, label, quality, request_type,
                    status, target_language
                )
                VALUES (
                    :id, :doc_id, :version_number, 'Auto-enrich', 'high',
                    'auto_enrich', 'pending', 'en'
                )
                """
            ),
            {
                "id": db_uuid(uuid4()),
                "doc_id": db_uuid(doc_id),
                "version_number": next_number,
            },
        )

        self._connection.execute(
            sa.text(
                """
                UPDATE documents
                SET translation_quality = 'pending_high'
                WHERE id = :id
                """
            ),
            {"id": db_uuid(doc_id)},
        )

    @staticmethod
    def _archive_snippet(path: Path) -> str:
        """List top-level filenames in an archive."""
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as zf:
                    names = [name for name in zf.namelist() if not name.endswith("/")]
                    return "\n".join(names[:50])  # limit to 50 files
            elif tarfile.is_tarfile(path):
                with tarfile.open(path) as tf:
                    names = [m.name for m in tf.getmembers() if m.isfile()]
                    return "\n".join(names[:50])
        except Exception:
            pass
        return ""

    @staticmethod
    def _sanitize_html(raw: str) -> str:
        """Strip dangerous tags and attributes from HTML."""
        # Remove script and style tags with content
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        # Remove event handlers
        raw = re.sub(r"\s*on\w+\s*=\s*['\"][^'\"]*['\"]", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*on\w+\s*=\s*[^\s>]+", "", raw, flags=re.IGNORECASE)
        # Remove javascript: URLs
        raw = re.sub(
            r"\s*(href|src|action)\s*=\s*['\"]javascript:[^'\"]*['\"]",
            r' \1=""',
            raw,
            flags=re.IGNORECASE,
        )
        # Remove data: URLs
        raw = re.sub(
            r"\s*(href|src|action)\s*=\s*['\"]data:[^'\"]*['\"]",
            r' \1=""',
            raw,
            flags=re.IGNORECASE,
        )
        # Remove iframe, object, embed tags
        raw = re.sub(
            r"<(iframe|object|embed)[^>]*>.*?</\1>",
            "",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        )
        raw = re.sub(r"<(iframe|object|embed)[^/]*/?>", "", raw, flags=re.IGNORECASE)
        return raw.strip()

    def get_user_activity(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return document view history for *user_id*."""
        rows = self._connection.execute(
            sa.text(
                """
                SELECT d.id, d.title, d.mime_type, v.viewed_at
                FROM document_views v
                JOIN documents d ON d.id = v.doc_id
                WHERE v.user_id = :user_id
                ORDER BY v.viewed_at DESC
                LIMIT :limit
                OFFSET :offset
                """
            ),
            {
                "user_id": db_uuid(user_id),
                "limit": limit,
                "offset": offset,
            },
        ).mappings()

        return [
            {
                "doc_id": str(UUID(str(row["id"]))),
                "title": row["title"],
                "mime_type": row["mime_type"],
                "viewed_at": str(row["viewed_at"]) if row["viewed_at"] else None,
            }
            for row in rows
        ]
