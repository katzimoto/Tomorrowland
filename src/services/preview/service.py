"""Document preview service with truncated snippets and view tracking."""

from __future__ import annotations

import html
import json
import logging
import tarfile
import zipfile
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa

from services.extraction.registry import ExtractorRegistry
from services.pipeline.jobs import PipelineJobRepository
from shared.db import db_uuid, to_uuid

logger = logging.getLogger(__name__)

SNIPPET_LENGTH = 2000

# Attributes that carry a URL and therefore need scheme validation.
_URL_ATTRS = frozenset({"href", "src", "action"})


def _is_safe_attr(name: str, value: str | None) -> bool:
    """Whitelist gate for an HTML attribute kept by the preview sanitizer.

    Drops event handlers (``on*``) and any attribute whose name is not a simple
    token (so a malformed name cannot break out of the tag). For URL-bearing
    attributes it rejects ``javascript:``/``data:``/``vbscript:`` schemes,
    collapsing embedded whitespace first so e.g. ``java\\tscript:`` cannot slip
    through. Values are escaped separately at render time.
    """
    key = name.lower()
    if key.startswith("on"):
        return False
    if not key or not all(c.isalnum() or c == "-" for c in key):
        return False
    if key in _URL_ATTRS:
        if not value:
            return False
        scheme = "".join(value.split()).lower()
        return not scheme.startswith(("javascript:", "data:", "vbscript:"))
    return True


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

        # Try stored payload text before re-extracting from file.
        # Temp files (SMB downloads, Atlassian attachments) are deleted
        # after pipeline processing, so file-based re-extraction would
        # always return "" for those sources.  The pipeline already stored
        # the content in document_payloads, so prefer that here.
        payload_row = (
            self._connection.execute(
                sa.text("SELECT content_text FROM document_payloads WHERE document_id = :id"),
                {"id": db_uuid(document_id)},
            )
            .mappings()
            .first()
        )
        if payload_row and payload_row["content_text"]:
            return str(payload_row["content_text"])[:SNIPPET_LENGTH]

        # Fall back to original document extraction (file still on disk)
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
        text = self._extractor.extract(path, mime_type).text

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
            try:
                threshold = int(threshold)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid auto_enrich.threshold=%r; using default 5", threshold
                )
                threshold = 5

        if view_count < threshold:
            return

        # Atomic insert: compute next version_number and insert in one statement.
        # ON CONFLICT with the partial unique index on (document_id, request_type)
        # WHERE status IN ('pending', 'running') ensures only one active
        # auto_enrich job exists per document — even under concurrent requests
        # that both pass the view-count threshold at the same time.
        result = self._connection.execute(
            sa.text("""
                INSERT INTO document_translation_versions (
                    id, document_id, version_number, label, quality, request_type,
                    status, target_language
                )
                SELECT
                    :id,
                    :document_id,
                    COALESCE(
                        (SELECT MAX(version_number)
                         FROM document_translation_versions
                         WHERE document_id = :document_id),
                        0
                    ) + 1,
                    'Auto-enrich',
                    'high',
                    'auto_enrich',
                    'pending',
                    COALESCE(
                        (SELECT target_language FROM documents WHERE id = :document_id),
                        'en'
                    )
                ON CONFLICT (document_id, request_type)
                WHERE status IN ('pending', 'running')
                DO NOTHING
                """),
            {
                "id": db_uuid(uuid4()),
                "document_id": db_uuid(document_id),
            },
        )
        if result.rowcount == 0:
            # Another request beat us to it — job already queued.
            return

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
        # Commit the auto-enrich state before publishing to RabbitMQ so the
        # enrich worker can see the pending_high status and the job row.
        self._connection.commit()

        if getattr(self, "_rabbit", None) is not None and getattr(self._rabbit, "_enabled", False):
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
            logger.debug("Failed to read archive file listing: %s", path)
        return ""

    @staticmethod
    def _sanitize_html(raw: str) -> str:
        """Extract visible text from HTML using a whitelist parser.

        Uses html.parser to safely extract text content while stripping
        dangerous tags (script, style, iframe, object, embed) and all
        event-handler attributes.  Safe inline tags like <b>, <i>, <em>,
        <strong>, <mark>, <code> are preserved for preview formatting.
        """
        from html.parser import HTMLParser

        safe_tags = frozenset(
            {
                "b",
                "i",
                "em",
                "strong",
                "p",
                "br",
                "ul",
                "ol",
                "li",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "code",
                "pre",
                "mark",
                "blockquote",
                "span",
                "div",
                "a",
                "table",
                "thead",
                "tbody",
                "tr",
                "td",
                "th",
                "hr",
            }
        )
        dangerous_tags = frozenset({"script", "style", "iframe", "object", "embed", "noscript"})

        class _SafeHTMLStripper(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self._result: list[str] = []
                self._skip_depth: int = 0

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag in dangerous_tags:
                    self._skip_depth += 1
                    return
                if self._skip_depth > 0:
                    return
                if tag in safe_tags:
                    # Escape values so an attribute cannot break out of its
                    # quotes and inject new attributes / event handlers.
                    attr_str = "".join(
                        f' {k}="{html.escape(v, quote=True)}"'
                        for k, v in attrs
                        if v is not None and _is_safe_attr(k, v)
                    )
                    self._result.append(f"<{tag}{attr_str}>")

            def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag in safe_tags and self._skip_depth == 0:
                    self._result.append(f"<{tag} />")

            def handle_endtag(self, tag: str) -> None:
                if tag in dangerous_tags and self._skip_depth > 0:
                    self._skip_depth -= 1
                    return
                if self._skip_depth > 0:
                    return
                if tag in safe_tags:
                    self._result.append(f"</{tag}>")

            def handle_data(self, data: str) -> None:
                if self._skip_depth == 0:
                    # Escape text so entity-encoded markup decoded by the parser
                    # (convert_charrefs) cannot be re-emitted as live HTML.
                    self._result.append(html.escape(data))

            def text(self) -> str:
                return "".join(self._result)

        parser = _SafeHTMLStripper()
        parser.feed(raw)
        return parser.text().strip()

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
