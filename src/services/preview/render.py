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
from services.preview.manifest import (
    build_base_manifest,
    classify_kind,
    worker_renderer,
)
from services.preview.msg_renderer import render_msg
from services.preview.office_pdf import (
    OfficeRenderError,
    build_office_manifest_section,
    render_office_pdf,
)
from services.preview.sheet_grid import render_sheets
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
    kind = classify_kind(doc.mime_type)
    renderer = worker_renderer(doc.mime_type)

    repo = PreviewArtifactRepository(connection)
    row = repo.get(document_id, sha)
    if row is None:
        row = repo.create_pending(document_id, sha, renderer=renderer or "text")
    if row.status in ("ready", "partial", "failed"):
        # Terminal — admin rerender deletes the row first; never re-render here.
        return row.status

    if renderer is None:
        repo.mark_failed(document_id, sha, error_category="unsupported_renderer")
        return "failed"

    repo.mark_running(document_id, sha)

    manifest = build_base_manifest(
        document_id=str(document_id),
        content_sha256=sha,
        kind=kind,
        renderer=renderer,
        status="ready",
        generated_at=_utc_now_iso(),
    )

    # Shared pre-render file checks.
    if doc.path is None or not (source_path := Path(doc.path)).is_file():
        repo.mark_failed(document_id, sha, error_category="not_found", manifest=manifest)
        return "failed"
    if source_path.stat().st_size > settings.preview_max_file_bytes:
        repo.mark_failed(document_id, sha, error_category="file_too_large", manifest=manifest)
        return "failed"

    if renderer == "libreoffice_pdf":
        return _render_office(repo, settings, document_id, sha, source_path, kind, manifest)
    if renderer == "sheet_grid":
        return _render_sheets(repo, settings, document_id, sha, source_path, manifest)
    return _render_email(repo, connection, settings, doc, document_id, sha, source_path, manifest)


def _render_email(
    repo: PreviewArtifactRepository,
    connection: sa.Connection,
    settings: Settings,
    doc: Any,
    document_id: UUID,
    sha: str,
    source_path: Path,
    manifest: dict[str, Any],
) -> str:
    try:
        if doc.mime_type == "application/vnd.ms-outlook":
            rendered = render_msg(
                source_path,
                max_inline_images=settings.preview_max_inline_images,
                max_inline_image_bytes=settings.preview_max_inline_image_bytes,
                rtf_timeout=settings.preview_render_timeout_seconds,
            )
        else:
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
        _persist_render_failure(repo, document_id, sha, "render", exc, manifest)
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


def _render_office(
    repo: PreviewArtifactRepository,
    settings: Settings,
    document_id: UUID,
    sha: str,
    source_path: Path,
    kind: str,
    manifest: dict[str, Any],
) -> str:
    try:
        rendered = render_office_pdf(
            source_path,
            timeout=settings.preview_render_timeout_seconds,
            max_pages=settings.preview_max_pages,
        )
        store = PreviewArtifactStore(settings.files_root)
        files = store.write_artifacts(document_id, sha, rendered.artifacts)
    except OfficeRenderError as exc:
        _persist_render_failure(repo, document_id, sha, exc.category, exc, manifest)
        return "failed"
    except Exception as exc:
        _persist_render_failure(repo, document_id, sha, "render", exc, manifest)
        return "failed"

    manifest["office"] = build_office_manifest_section(rendered)
    manifest["artifacts"] = [
        {
            "id": "converted-pdf",
            "role": "office_pdf",
            "content_type": "application/pdf",
            "size_bytes": len(rendered.artifacts["converted-pdf"][2]),
        }
    ]
    manifest["navigation"] = {
        "unit": "slide" if kind == "office_slides" else "page",
        "count": rendered.page_count or 0,
        "items": [],
    }
    # Page count over the cap renders the available pages but flags partial.
    status = "partial" if rendered.truncated else "ready"
    manifest["status"] = status
    repo.mark_rendered(document_id, sha, status=status, manifest=manifest, files=files)
    return status


def _render_sheets(
    repo: PreviewArtifactRepository,
    settings: Settings,
    document_id: UUID,
    sha: str,
    source_path: Path,
    manifest: dict[str, Any],
) -> str:
    try:
        rendered = render_sheets(
            source_path,
            max_rows=settings.preview_max_sheet_rows,
            max_cols=settings.preview_max_sheet_cols,
        )
        store = PreviewArtifactStore(settings.files_root)
        files = store.write_artifacts(document_id, sha, rendered.artifacts)
    except Exception as exc:
        _persist_render_failure(repo, document_id, sha, "render", exc, manifest)
        return "failed"

    manifest["artifacts"] = [
        {
            "id": artifact_id,
            "role": "sheet_grid",
            "content_type": "application/json",
            "size_bytes": len(data),
        }
        for artifact_id, (_filename, _ctype, data) in rendered.artifacts.items()
    ]
    manifest["navigation"] = {
        "unit": "sheet",
        "count": len(rendered.sheets),
        "items": rendered.sheets,
    }
    status = "partial" if rendered.truncated else "ready"
    manifest["status"] = status
    repo.mark_rendered(document_id, sha, status=status, manifest=manifest, files=files)
    return status


def _persist_render_failure(
    repo: PreviewArtifactRepository,
    document_id: UUID,
    sha: str,
    category: str,
    exc: BaseException,
    manifest: dict[str, Any],
) -> None:
    logger.warning(
        "preview render failed: document_id=%s category=%s error=%s",
        document_id,
        category,
        str(exc).split("\n")[0],
    )
    repo.mark_failed(
        document_id,
        sha,
        error_category=category,
        error_detail=f"{type(exc).__name__}: {str(exc).split(chr(10))[0]}",
        manifest=manifest,
    )
