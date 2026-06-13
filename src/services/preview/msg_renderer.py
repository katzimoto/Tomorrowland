"""MSG (Outlook) → preview artifacts renderer.

Uses ``extract_msg`` (a core dependency) to read the MAPI message, then emits
the same artifacts and manifest ``email`` section as the EML renderer so the
frontend EmailViewer renders both identically. Reduced fidelity vs. EML:
Outlook stores either an HTML body or an RTF-only body; the RTF-only case
degrades to the plain-text body (RTF→HTML conversion is a staged follow-up).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import extract_msg

from services.preview.email_common import (
    RenderedEmail,
    assemble_email_manifest,
    cid_to_data_uri,
    detect_quoted_ranges,
)
from services.preview.sanitizer import sanitize_email_html

logger = logging.getLogger(__name__)


def _safe_str(value: object | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value).strip()


def _address_list(value: object | None) -> list[str]:
    """Split an Outlook recipient string (``;``/``,`` separated) into addresses."""
    text = _safe_str(value)
    if not text:
        return []
    parts = [p.strip() for chunk in text.split(";") for p in chunk.split(",")]
    return [p for p in parts if p]


def _date_iso(value: object | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return _safe_str(value) or None


def _attachment_cid(att: object) -> str | None:
    """Content-ID of an inline attachment, if any (sans angle brackets)."""
    for attr in ("cid", "contentId", "content_id"):
        raw = getattr(att, attr, None)
        if raw:
            return _safe_str(raw).strip("<>")
    return None


def _attachment_bytes(att: object) -> bytes | None:
    raw = getattr(att, "data", None)
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) and raw else None


def _attachment_name(att: object) -> str:
    return (
        getattr(att, "longFilename", None)
        or getattr(att, "filename", None)
        or getattr(att, "shortFilename", None)
        or getattr(att, "name", None)
        or "(unnamed)"
    )


def _attachment_ctype(att: object) -> str:
    return (
        getattr(att, "mimetype", None)
        or getattr(att, "content_type", None)
        or getattr(att, "mime_type", None)
        or "application/octet-stream"
    )


def render_msg(
    path: Path,
    *,
    max_inline_images: int,
    max_inline_image_bytes: int,
) -> RenderedEmail:
    """Render an Outlook .msg file into preview artifacts and the manifest."""
    msg = extract_msg.Message(str(path))  # type: ignore[no-untyped-call]
    try:
        return _render_open_msg(
            msg,
            max_inline_images=max_inline_images,
            max_inline_image_bytes=max_inline_image_bytes,
        )
    finally:
        try:
            msg.close()
        except Exception:
            logger.debug("failed to close MSG message", exc_info=True)


def _render_open_msg(
    msg: Any,
    *,
    max_inline_images: int,
    max_inline_image_bytes: int,
) -> RenderedEmail:
    # Partition attachments into inline images (referenced by cid) and regular
    # attachments, respecting the inline-image caps.
    cid_data_uris: dict[str, str] = {}
    inline_meta: list[dict[str, Any]] = []
    skipped_inline = 0
    attachment_entries: list[dict[str, Any]] = []

    for att in getattr(msg, "attachments", None) or []:
        cid = _attachment_cid(att)
        ctype = _attachment_ctype(att)
        data = _attachment_bytes(att)
        is_inline_image = bool(cid) and ctype.startswith("image/")
        if is_inline_image:
            assert cid is not None
            if (
                data is None
                or len(data) > max_inline_image_bytes
                or len(inline_meta) >= max_inline_images
            ):
                skipped_inline += 1
                continue
            cid_data_uris[cid] = cid_to_data_uri(ctype, data)
            inline_meta.append(
                {
                    "content_id": cid,
                    "content_type": ctype,
                    "size_bytes": len(data),
                    "embedded": True,
                }
            )
        else:
            attachment_entries.append(
                {
                    "filename": _attachment_name(att),
                    "content_type": ctype,
                    "size_bytes": len(data) if data is not None else None,
                    "document_id": None,
                    "preview_available": False,
                    "inline": False,
                }
            )

    artifacts: dict[str, tuple[str, str, bytes]] = {}
    blocked_remote_images = 0
    embedded_count = 0

    html_body = _safe_str(getattr(msg, "htmlBody", None) or getattr(msg, "html", None))
    if html_body:
        sanitized = sanitize_email_html(html_body, cid_data_uris)
        artifacts["body-html"] = ("body.html", "text/html", sanitized.html.encode("utf-8"))
        blocked_remote_images = sanitized.blocked_remote_images
        embedded_count = sanitized.embedded_inline_images

    text_body = _safe_str(getattr(msg, "body", None))
    quoted_ranges: list[dict[str, Any]] = []
    if text_body:
        artifacts["body-text"] = ("body.txt", "text/plain", text_body.encode("utf-8"))
        quoted_ranges = detect_quoted_ranges(text_body)

    email_manifest = assemble_email_manifest(
        subject=_safe_str(getattr(msg, "subject", None)),
        from_=_safe_str(getattr(msg, "sender", None)),
        to=_address_list(getattr(msg, "to", None)),
        cc=_address_list(getattr(msg, "cc", None)),
        bcc=_address_list(getattr(msg, "bcc", None)),
        date=_date_iso(getattr(msg, "date", None)),
        message_id=_safe_str(getattr(msg, "messageId", None)),
        in_reply_to=_safe_str(getattr(msg, "inReplyTo", None)),
        has_html_body="body-html" in artifacts,
        has_text_body="body-text" in artifacts,
        quoted_ranges=quoted_ranges,
        inline_images=inline_meta,
        skipped_inline_images=skipped_inline,
        blocked_remote_images=blocked_remote_images,
        embedded_inline_images=embedded_count,
        attachments=attachment_entries,
    )
    return RenderedEmail(artifacts=artifacts, email_manifest=email_manifest)
