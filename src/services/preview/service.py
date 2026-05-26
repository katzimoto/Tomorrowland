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
from services.pipeline.jobs import PipelineJobRepository
from shared.db import db_uuid, to_uuid

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
        rabbit: Any = None,
    ) -> None:
        self._connection = connection
        self._extractor = extractor_registry or ExtractorRegistry()
        self._rabbit = rabbit

    def get_preview(
        self,
        document_id: UUID,
        user_id: UUID,
        translation_version_id: UUID | None = None,
        show_original: bool = False,
    ) -> dict[str, Any]:
        """Return preview metadata, snippet, and view count for *document_id*.

        Also records a view by *user_id* if not already present.
        If *translation_version_id* is provided and the version is available,
        the snippet is rendered from the stored translated text.
        When *show_original* is True, skip all translation resolution and
        render from the original file extraction.
        """

        row = (
            self._connection.execute(
                sa.text("""
                    SELECT id, source_id, title, mime_type, path, translation_quality, metadata
                    FROM documents WHERE id = :id
                    """),
                {"id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        if row is None:
            return {}

        # Record view (deduplicated by document_id + user_id)
        self._connection.execute(
            sa.text("""
                INSERT INTO document_views (id, document_id, user_id, viewed_at)
                VALUES (:id, :document_id, :user_id, CURRENT_TIMESTAMP)
                ON CONFLICT DO NOTHING
                """),
            {
                "id": db_uuid(uuid4()),
                "document_id": db_uuid(document_id),
                "user_id": db_uuid(user_id),
            },
        )

        # Get global view count
        view_count = self._connection.execute(
            sa.text("SELECT COUNT(*) FROM document_views WHERE document_id = :document_id"),
            {"document_id": db_uuid(document_id)},
        ).scalar_one()

        # Auto-enrich: queue for high-quality translation when view threshold is crossed
        self._maybe_auto_enrich(
            document_id, row["source_id"], view_count, row["translation_quality"]
        )

        snippet = self._generate_snippet(
            document_id,
            row["path"],
            row["mime_type"],
            translation_version_id,
            show_original=show_original,
        )

        return {
            "document_id": str(document_id),
            "title": row["title"],
            "mime_type": row["mime_type"],
            "translation_quality": row["translation_quality"],
            "metadata": _parse_metadata(row["metadata"]),
            "snippet": snippet,
            "view_count": view_count,
        }

    def get_full_text(
        self,
        document_id: UUID,
        translation_version_id: UUID | None = None,
        show_original: bool = False,
    ) -> str:
        """Return the full resolved text for *document_id* without truncation.

        Resolution priority matches _generate_snippet:
        1. If show_original=True, skip translation and use content_text.
        2. Otherwise try get_translated_text (version → latest → legacy payload).
        3. Fall back to document_payloads.content_text.
        4. Return "" if nothing is found.
        """
        if not show_original:
            translated = self.get_translated_text(
                document_id, translation_version_id=translation_version_id
            )
            if translated:
                return translated

        payload_row = (
            self._connection.execute(
                sa.text("SELECT content_text FROM document_payloads WHERE document_id = :id"),
                {"id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        if payload_row and payload_row["content_text"]:
            return str(payload_row["content_text"])
        return ""

    def get_translated_text(
        self,
        document_id: UUID,
        translation_version_id: UUID | None = None,
    ) -> str | None:
        """Resolve the full translated text for *document_id*.

        When *translation_version_id* is provided and the version is
        available and belongs to the same document, returns that version's
        translated text.  When omitted, returns the latest available
        translation.  Falls back to ``document_payloads.translated_text``
        for documents processed before version records existed.
        Returns ``None`` when no translation is found.

        In all three lookup paths, versions / payloads whose
        ``translated_text`` equals the original ``content_text`` are
        skipped — they represent no-op translations (document already in the
        target language or LibreTranslate returned the input unchanged) and
        would otherwise show original-language text in the translation view.
        """
        if translation_version_id is not None:
            version_row = (
                self._connection.execute(
                    sa.text("""
                        SELECT dv.translated_text, dv.document_id
                        FROM document_translation_versions dv
                        LEFT JOIN document_payloads dp
                               ON dp.document_id = dv.document_id
                        WHERE dv.id = :id
                          AND dv.status = 'available'
                          AND (
                            dp.content_text IS NULL
                            OR dv.translated_text IS DISTINCT FROM dp.content_text
                          )
                        """),
                    {"id": db_uuid(translation_version_id)},
                )
                .mappings()
                .first()
            )
            if (
                version_row is not None
                and to_uuid(version_row["document_id"]) == document_id
                and version_row["translated_text"]
            ):
                return str(version_row["translated_text"])

        latest_row = (
            self._connection.execute(
                sa.text("""
                    SELECT dtv.translated_text
                    FROM document_translation_versions dtv
                    LEFT JOIN document_payloads dp
                           ON dp.document_id = dtv.document_id
                    WHERE dtv.document_id = :document_id
                      AND dtv.status = 'available'
                      AND (
                        dp.content_text IS NULL
                        OR dtv.translated_text IS DISTINCT FROM dp.content_text
                      )
                    ORDER BY dtv.version_number DESC
                    LIMIT 1
                    """),
                {"document_id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        if latest_row and latest_row["translated_text"]:
            return str(latest_row["translated_text"])

        payload_row = (
            self._connection.execute(
                sa.text("""
                    SELECT translated_text
                    FROM document_payloads
                    WHERE document_id = :document_id
                      AND (
                        content_text IS NULL
                        OR translated_text IS DISTINCT FROM content_text
                      )
                    """),
                {"document_id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        if payload_row and payload_row["translated_text"]:
            return str(payload_row["translated_text"])

        return None

    def _generate_snippet(
        self,
        document_id: UUID,
        file_path: str | None,
        mime_type: str,
        translation_version_id: UUID | None = None,
        show_original: bool = False,
    ) -> str:
        """Return a truncated preview snippet for a document.

        When *translation_version_id* is provided, renders that version
        only if it is ``available`` and belongs to the same document.
        When omitted, resolves the latest available translation for the
        document (ordered by highest ``version_number``). Falls back to
        ``document_payloads.translated_text`` for documents that were
        processed before version records existed, then to the original
        file extraction.
        When *show_original* is True, skip all translation resolution and
        always fall through to the original file extraction.
        """
        if not show_original:
            translated_text = self.get_translated_text(
                document_id, translation_version_id=translation_version_id
            )
            if translated_text:
                return translated_text[:SNIPPET_LENGTH]

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
        document_id: UUID,
        source_id: UUID,
        view_count: int,
        current_quality: str | None,
    ) -> None:
        """Queue document for enrichment if view threshold is crossed.

        Creates a translation version record and enqueues an
        ``enrich_document`` pipeline job for the slow worker.
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
            sa.text("""
                    SELECT id FROM document_translation_versions
                    WHERE document_id = :document_id
                      AND request_type = 'auto_enrich'
                      AND status IN ('pending', 'running')
                    LIMIT 1
                    """),
            {"document_id": db_uuid(document_id)},
        ).scalar_one_or_none()
        if existing:
            return

        # Create auto_enrich version
        next_number = self._connection.execute(
            sa.text("""
                    SELECT COALESCE(MAX(version_number), 0) + 1
                    FROM document_translation_versions
                    WHERE document_id = :document_id
                    """),
            {"document_id": db_uuid(document_id)},
        ).scalar_one()

        self._connection.execute(
            sa.text("""
                INSERT INTO document_translation_versions (
                    id, document_id, version_number, label, quality, request_type,
                    status, target_language
                )
                VALUES (
                    :id, :document_id, :version_number, 'Auto-enrich', 'high',
                    'auto_enrich', 'pending', 'en'
                )
                """),
            {
                "id": db_uuid(uuid4()),
                "document_id": db_uuid(document_id),
                "version_number": next_number,
            },
        )

        self._connection.execute(
            sa.text("""
                UPDATE documents
                SET translation_quality = 'pending_high'
                WHERE id = :id
                """),
            {"id": db_uuid(document_id)},
        )

        job_repo = PipelineJobRepository(self._connection)
        job_id = job_repo.enqueue_document(
            document_id=document_id,
            source_id=source_id,
            job_type="enrich_document",
        )

        if getattr(self, "_rabbit", None) is not None and self._rabbit._enabled:
            from services.pipeline.publisher import DocumentPublisher

            publisher = DocumentPublisher(job_repo=job_repo, rabbit=self._rabbit)
            publisher.publish_enrich(
                job_id=job_id,
                document_id=document_id,
                source_id=source_id,
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
        group_ids: list[UUID] | None = None,
        allow_all: bool = False,
    ) -> list[dict[str, Any]]:
        """Return document view history for *user_id*.

        When *allow_all* is False (non-admin callers), only documents still
        accessible via the caller's current group memberships are returned.
        This prevents stale activity rows from leaking documents to users
        whose group access has since been revoked.

        Args:
            user_id: The user whose activity to return.
            limit: Maximum rows to return.
            offset: Pagination offset.
            group_ids: Caller's effective group IDs (used when allow_all=False).
            allow_all: When True (admin), skip the group filter.
        """
        if allow_all or not group_ids:
            rows = self._connection.execute(
                sa.text("""
                    SELECT d.id, d.title, d.mime_type, v.viewed_at
                    FROM document_views v
                    JOIN documents d ON d.id = v.document_id
                    WHERE v.user_id = :user_id
                    ORDER BY v.viewed_at DESC
                    LIMIT :limit
                    OFFSET :offset
                    """),
                {
                    "user_id": db_uuid(user_id),
                    "limit": limit,
                    "offset": offset,
                },
            ).mappings()
        else:
            rows = self._connection.execute(
                sa.text("""
                    SELECT DISTINCT d.id, d.title, d.mime_type, v.viewed_at
                    FROM document_views v
                    JOIN documents d ON d.id = v.document_id
                    JOIN source_permissions sp ON sp.source_id = d.source_id
                    WHERE v.user_id = :user_id
                      AND sp.group_id IN :group_ids
                    ORDER BY v.viewed_at DESC
                    LIMIT :limit
                    OFFSET :offset
                    """).bindparams(sa.bindparam("group_ids", expanding=True)),
                {
                    "user_id": db_uuid(user_id),
                    "group_ids": [db_uuid(g) for g in group_ids],
                    "limit": limit,
                    "offset": offset,
                },
            ).mappings()

        return [
            {
                "document_id": str(UUID(str(row["id"]))),
                "title": row["title"],
                "mime_type": row["mime_type"],
                "viewed_at": str(row["viewed_at"]) if row["viewed_at"] else None,
            }
            for row in rows
        ]
