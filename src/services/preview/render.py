"""Preview render orchestration — load document, render, persist artifacts.

Called by the preview worker (RabbitMQ path) and directly by tests. Render
failures are persisted as terminal artifact states and never raised: a broken
file must not bounce a pipeline job through retry/dead-letter forever.
Infrastructure errors (DB unavailable, disk full) DO raise so the normal job
retry machinery applies.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from services.documents.repository import (
    DocumentRelationshipRepository,
    DocumentRepository,
)
from services.preview.artifact_repository import PreviewArtifactRepository
from services.preview.artifact_store import PreviewArtifactStore
from services.preview.email_renderer import render_email
from services.preview.manifest import build_base_manifest, renders_via_worker
from shared.config import Settings

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_attachment_documents(
    connection: sa.Connection, document_id: UUID, attachments: list[dict[str, Any]]
) -> None:
    """Match manifest attachment entries to child documents by filename.

    Duplicate filenames match in listed order — a known ambiguity until
    parse_worker records the attachment index in path_in_parent (plan risk #6).
    """
    rel_repo = DocumentRelationshipRepository(connection)
    unclaimed = rel_repo.get_child_relationships(document_id, relationship_type="attachment")
    for entry in attachments:
        for rel in unclaimed:
            if rel.get("path_in_parent") == entry["filename"]:
                entry["document_id"] = str(rel["other_document_id"])
                entry["preview_available"] = True
                unclaimed.remove(rel)
                break


def render_document_preview(
    connection: sa.Connection,
    settings: Settings,
    document_id: UUID,
) -> str:
    """Render preview artifacts for one document; returns the final status."""
    doc_repo = DocumentRepository(connection)
    doc = doc_repo.get_by_id(document_id)
    if doc is None:
        logger.warning("preview render: document not found id=%s", document_id)
        return "failed"

    sha = doc.content_sha256 or ""
    repo = PreviewArtifactRepository(connection)
    row = repo.get(document_id, sha)
    if row is None:
        row = repo.create_pending(document_id, sha, renderer="email")
    if row.status in ("ready", "partial", "failed"):
        # Terminal — admin rerender deletes the row first; never re-render here.
        return row.status

    if not renders_via_worker(doc.mime_type):
        repo.mark_failed(document_id, sha, error_category="unsupported_renderer")
        return "failed"

    repo.mark_running(document_id, sha)

    manifest = build_base_manifest(
        document_id=str(document_id),
        content_sha256=sha,
        kind="email",
        renderer="email",
        status="ready",
        generated_at=_utc_now_iso(),
    )

    if doc.path is None:
        repo.mark_failed(document_id, sha, error_category="not_found", manifest=manifest)
        return "failed"
    source_path = Path(doc.path)
    if not source_path.is_file():
        repo.mark_failed(document_id, sha, error_category="not_found", manifest=manifest)
        return "failed"
    if source_path.stat().st_size > settings.preview_max_file_bytes:
        repo.mark_failed(document_id, sha, error_category="file_too_large", manifest=manifest)
        return "failed"

    try:
        rendered = render_email(
            source_path.read_bytes(),
            max_inline_images=settings.preview_max_inline_images,
            max_inline_image_bytes=settings.preview_max_inline_image_bytes,
        )
        _resolve_attachment_documents(
            connection, document_id, rendered.email_manifest["attachments"]
        )
        store = PreviewArtifactStore(settings.files_root)
        files = store.write_artifacts(document_id, sha, rendered.artifacts)
    except Exception as exc:
        # Deterministic render failure (malformed file, encoding bombs, …) —
        # terminal by design so the job machinery never loops on it.
        logger.warning(
            "preview render failed: document_id=%s error=%s",
            document_id,
            str(exc).split("\n")[0],
        )
        repo.mark_failed(
            document_id,
            sha,
            error_category="render",
            error_detail=f"{type(exc).__name__}: {str(exc).split(chr(10))[0]}",
            manifest=manifest,
        )
        return "failed"

    manifest["email"] = rendered.email_manifest
    manifest["artifacts"] = [
        {
            "id": artifact_id,
            "role": "email_body_html" if artifact_id == "body-html" else "email_body_text",
            "content_type": content_type,
            "size_bytes": len(data),
        }
        for artifact_id, (_filename, content_type, data) in rendered.artifacts.items()
    ]

    # No HTML and no text body → partial: headers still render, bodies don't.
    status = "partial" if not rendered.artifacts else "ready"
    manifest["status"] = status
    repo.mark_rendered(document_id, sha, status=status, manifest=manifest, files=files)
    return status
