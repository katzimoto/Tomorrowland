"""EML → preview artifacts renderer.

Parses the original RFC 822 bytes with the stdlib ``email`` package (the
extraction-side ``EmlExtractor`` flattens to text and is deliberately not
reused — preview needs the MIME tree). Produces sanitized HTML and plain-text
body artifacts plus the manifest ``email`` section. Inline ``cid:`` images
are embedded as ``data:`` URIs (see sanitizer module for why).
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Any

from services.preview.sanitizer import sanitize_email_html

logger = logging.getLogger(__name__)

# Quoted-reply / thread-history markers (text bodies). Heuristic only: a
# wrong match degrades to "section shown expanded", never to data loss.
_QUOTE_MARKERS = (
    re.compile(r"^On .{4,200} wrote:\s*$"),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}$", re.IGNORECASE),
)


@dataclass(frozen=True)
class RenderedEmail:
    """Renderer output consumed by the render orchestrator."""

    # artifact_id -> (relative filename, content type, bytes)
    artifacts: dict[str, tuple[str, str, bytes]]
    # The manifest "email" section.
    email_manifest: dict[str, Any]


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


def detect_quoted_ranges(text: str) -> list[dict[str, Any]]:
    """Line ranges of quoted replies / thread history in a text body."""
    lines = text.splitlines()
    ranges: list[dict[str, Any]] = []
    marker_start: int | None = None
    marker_label = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if marker_start is None:
            for pattern in _QUOTE_MARKERS:
                if pattern.match(stripped):
                    marker_start = idx
                    marker_label = stripped[:120]
                    break
    if marker_start is not None:
        ranges.append(
            {"start_line": marker_start, "end_line": len(lines) - 1, "label": marker_label}
        )
        return ranges

    # No marker: a trailing run of ">"-prefixed lines is still a quote block.
    quote_start: int | None = None
    for idx, line in enumerate(lines):
        if line.lstrip().startswith(">"):
            if quote_start is None:
                quote_start = idx
        elif line.strip():
            quote_start = None
    if quote_start is not None and quote_start < len(lines) - 1:
        ranges.append({"start_line": quote_start, "end_line": len(lines) - 1, "label": ""})
    return ranges


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
        cid: f"data:{img.content_type};base64,{base64.b64encode(img.data).decode('ascii')}"
        for cid, img in inline_images.items()
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

    email_manifest: dict[str, Any] = {
        "subject": _decoded_str(msg.get("Subject")) or None,
        "from": _decoded_str(msg.get("From")) or None,
        "to": _address_list(msg, "To"),
        "cc": _address_list(msg, "Cc"),
        "bcc": _address_list(msg, "Bcc"),
        "date": _header_date_iso(msg),
        "message_id": _decoded_str(msg.get("Message-ID")) or None,
        "in_reply_to": _decoded_str(msg.get("In-Reply-To")) or None,
        "has_html_body": "body-html" in artifacts,
        "has_text_body": "body-text" in artifacts,
        "quoted_ranges": quoted_ranges,
        "inline_images": [
            {
                "content_id": img.content_id,
                "content_type": img.content_type,
                "size_bytes": len(img.data),
                "embedded": True,
            }
            for img in inline_images.values()
        ],
        "skipped_inline_images": skipped_images,
        "blocked_remote_images": blocked_remote_images,
        "embedded_inline_images": embedded_count,
        "attachments": _attachment_entries(msg),
    }
    return RenderedEmail(artifacts=artifacts, email_manifest=email_manifest)
