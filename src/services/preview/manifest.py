"""Preview kind/renderer classification and manifest assembly helpers.

The preview manifest is the per-document-version contract between the
renderer pipeline and the frontend viewers. Kinds map a MIME type onto a
preview strategy; renderers name the component that produced (or will
produce) the artifacts. See docs/planning/preview-mail-office-first-2026-06.md.
"""

from __future__ import annotations

from typing import Any, Literal

PreviewKind = Literal[
    "email",
    "office_doc",
    "office_slides",
    "office_sheets",
    "pdf",
    "image",
    "text",
]
PreviewStatus = Literal["pending", "running", "ready", "partial", "failed"]

# Only EML renders through the preview worker in S1. MSG joins in S3 and the
# Office kinds in S4/S5; until then they report an honest text fallback so the
# manifest never strands a document in "pending".
RENDERED_EMAIL_MIMES = {"message/rfc822"}

_OFFICE_DOC_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.oasis.opendocument.text",
    "text/rtf",
    "application/rtf",
}
_OFFICE_SLIDES_MIMES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "application/vnd.oasis.opendocument.presentation",
}
_OFFICE_SHEETS_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.oasis.opendocument.spreadsheet",
}

# Default polling hint returned while a render job is in flight.
PENDING_RETRY_AFTER_MS = 1500


def classify_kind(mime_type: str) -> PreviewKind:
    """Map a MIME type onto the preview kind driving renderer dispatch."""
    mime = (mime_type or "").lower().split(";")[0].strip()
    if mime in RENDERED_EMAIL_MIMES or mime == "application/vnd.ms-outlook":
        return "email"
    if mime in _OFFICE_DOC_MIMES:
        return "office_doc"
    if mime in _OFFICE_SLIDES_MIMES:
        return "office_slides"
    if mime in _OFFICE_SHEETS_MIMES:
        return "office_sheets"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("image/"):
        return "image"
    return "text"


def renders_via_worker(mime_type: str) -> bool:
    """True when this MIME type produces artifacts via the preview worker."""
    mime = (mime_type or "").lower().split(";")[0].strip()
    return mime in RENDERED_EMAIL_MIMES


def immediate_renderer(kind: PreviewKind) -> str:
    """Renderer label for kinds served without artifacts (ready immediately)."""
    if kind == "pdf":
        return "pdfjs"
    if kind == "image":
        return "image"
    return "text"


def build_base_manifest(
    *,
    document_id: str,
    content_sha256: str,
    kind: PreviewKind,
    renderer: str,
    status: PreviewStatus,
    generated_at: str,
) -> dict[str, Any]:
    """Common manifest skeleton shared by all kinds."""
    manifest: dict[str, Any] = {
        "document_id": document_id,
        "cache_key": f"sha256:{content_sha256}" if content_sha256 else None,
        "kind": kind,
        "renderer": renderer,
        "status": status,
        "error": None,
        "generated_at": generated_at,
        "navigation": {"unit": "none", "count": 0, "items": []},
        "artifacts": [],
        "email": None,
        "office": None,
        "evidence": {
            "supports_text_search": True,
            "anchor_unit": "page" if kind in ("pdf", "office_doc", "office_slides") else "body",
            "regions_available": False,
        },
    }
    if kind in ("office_doc", "office_slides", "office_sheets"):
        manifest["office"] = {"pdf_artifact_id": None, "page_count": None, "text_fallback": True}
    return manifest
