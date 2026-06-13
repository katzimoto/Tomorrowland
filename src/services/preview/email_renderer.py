"""EML → preview artifacts renderer.

Parses the original RFC 822 bytes with the stdlib ``email`` package (the
extraction-side ``EmlExtractor`` flattens to text and is deliberately not
reused — preview needs the MIME tree). Produces sanitized HTML and plain-text
body artifacts plus the manifest ``email`` section. Inline ``cid:`` images
are embedded as ``data:`` URIs (see sanitizer module for why).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Any

from services.preview.email_common import (
    RenderedEmail,
    assemble_email_manifest,
    cid_to_data_uri,
    detect_quoted_ranges,
)
from services.preview.sanitizer import sanitize_email_html

logger = logging.getLogger(__name__)

# Re-exported for backward compatibility with existing imports/tests.
__all__ = ["RenderedEmail", "detect_quoted_ranges", "render_email"]


@dataclass
class _InlineImage:
    content_id: str
    content_type: str
    data: bytes = field(repr=False, default=b"")


def _decoded_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _address_list(msg: EmailMessage, header: str) -> list[str]:
    raw = msg.get_all(header, [])
    out: list[str] = []
    for entry in raw:
        text = _decoded_str(entry)
        if text:
            out.extend(part.strip() for part in text.split(",") if part.strip())
    return out


def _header_date_iso(msg: EmailMessage) -> str | None:
    raw = msg.get("Date")
    if raw is None:
        return None
    try:
        return parsedate_to_datetime(str(raw)).isoformat()
    except (TypeError, ValueError):
        return _decoded_str(raw) or None


def _collect_inline_images(
    msg: EmailMessage,
    *,
    max_images: int,
    max_image_bytes: int,
) -> tuple[dict[str, _InlineImage], int]:
    """Inline images by Content-ID; returns (kept, skipped_over_limits)."""
    kept: dict[str, _InlineImage] = {}
    skipped = 0
    for part in msg.walk():
        content_id = part.get("Content-ID")
        if content_id is None or not part.get_content_type().startswith("image/"):
            continue
        cid = str(content_id).strip().strip("<>")
        if not cid or cid in kept:
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:  # malformed transfer encoding — skip, never fail render
            logger.warning("undecodable inline image part: cid=%s", cid)
            skipped += 1
            continue
        if not isinstance(payload, bytes) or not payload:
            skipped += 1
            continue
        if len(payload) > max_image_bytes or len(kept) >= max_images:
            skipped += 1
            continue
        kept[cid] = _InlineImage(
            content_id=cid,
            content_type=part.get_content_type(),
            data=payload,
        )
    return kept, skipped


def _body_text(msg: EmailMessage, subtype: str) -> str | None:
    body = msg.get_body(preferencelist=(subtype,))
    if body is None:
        return None
    try:
        content = body.get_content()
    except Exception:
        logger.warning("undecodable %s body part", subtype)
        return None
    return content if isinstance(content, str) else None


def _attachment_entries(msg: EmailMessage) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for part in msg.iter_attachments():
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            payload = None
        size = len(payload) if isinstance(payload, bytes) else None
        entries.append(
            {
                "filename": part.get_filename() or "(unnamed)",
                "content_type": part.get_content_type(),
                "size_bytes": size,
                "document_id": None,  # resolved against document_relationships by the caller
                "preview_available": False,
                "inline": False,
            }
        )
    return entries


def render_email(
    raw: bytes,
    *,
    max_inline_images: int,
    max_inline_image_bytes: int,
) -> RenderedEmail:
    """Render EML bytes into preview artifacts and the manifest email section."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)

    inline_images, skipped_images = _collect_inline_images(
        msg, max_images=max_inline_images, max_image_bytes=max_inline_image_bytes
    )
    cid_data_uris = {
        cid: cid_to_data_uri(img.content_type, img.data) for cid, img in inline_images.items()
    }

    artifacts: dict[str, tuple[str, str, bytes]] = {}
    blocked_remote_images = 0
    embedded_count = 0

    html_body = _body_text(msg, "html")
    if html_body:
        sanitized = sanitize_email_html(html_body, cid_data_uris)
        artifacts["body-html"] = ("body.html", "text/html", sanitized.html.encode("utf-8"))
        blocked_remote_images = sanitized.blocked_remote_images
        embedded_count = sanitized.embedded_inline_images

    text_body = _body_text(msg, "plain")
    quoted_ranges: list[dict[str, Any]] = []
    if text_body:
        artifacts["body-text"] = ("body.txt", "text/plain", text_body.encode("utf-8"))
        quoted_ranges = detect_quoted_ranges(text_body)

    email_manifest = assemble_email_manifest(
        subject=_decoded_str(msg.get("Subject")),
        from_=_decoded_str(msg.get("From")),
        to=_address_list(msg, "To"),
        cc=_address_list(msg, "Cc"),
        bcc=_address_list(msg, "Bcc"),
        date=_header_date_iso(msg),
        message_id=_decoded_str(msg.get("Message-ID")),
        in_reply_to=_decoded_str(msg.get("In-Reply-To")),
        has_html_body="body-html" in artifacts,
        has_text_body="body-text" in artifacts,
        quoted_ranges=quoted_ranges,
        inline_images=[
            {
                "content_id": img.content_id,
                "content_type": img.content_type,
                "size_bytes": len(img.data),
                "embedded": True,
            }
            for img in inline_images.values()
        ],
        skipped_inline_images=skipped_images,
        blocked_remote_images=blocked_remote_images,
        embedded_inline_images=embedded_count,
        attachments=_attachment_entries(msg),
    )
    return RenderedEmail(artifacts=artifacts, email_manifest=email_manifest)
