"""Shared helpers for the EML and MSG preview renderers.

Both renderers parse different on-disk formats (stdlib ``email`` MIME tree vs.
``extract_msg`` MAPI) but emit the same manifest ``email`` section and the same
artifact set, so the manifest shaping and inline-image encoding live here to
keep the two in lockstep.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderedEmail:
    """Renderer output consumed by the render orchestrator (EML and MSG)."""

    # artifact_id -> (relative filename, content type, bytes)
    artifacts: dict[str, tuple[str, str, bytes]]
    # The manifest "email" section.
    email_manifest: dict[str, Any]


# Quoted-reply / thread-history markers (text bodies). Heuristic only: a wrong
# match degrades to "section shown expanded", never to data loss.
_QUOTE_MARKERS = (
    re.compile(r"^On .{4,200} wrote:\s*$"),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}$", re.IGNORECASE),
)


def cid_to_data_uri(content_type: str, data: bytes) -> str:
    """Encode inline-image bytes as a ``data:`` URI for embedding in HTML."""
    return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"


def detect_quoted_ranges(text: str) -> list[dict[str, Any]]:
    """Line ranges of quoted replies / thread history in a text body."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        for pattern in _QUOTE_MARKERS:
            if pattern.match(stripped):
                return [{"start_line": idx, "end_line": len(lines) - 1, "label": stripped[:120]}]

    # No marker: a trailing run of ">"-prefixed lines is still a quote block.
    quote_start: int | None = None
    for idx, line in enumerate(lines):
        if line.lstrip().startswith(">"):
            if quote_start is None:
                quote_start = idx
        elif line.strip():
            quote_start = None
    if quote_start is not None and quote_start < len(lines) - 1:
        return [{"start_line": quote_start, "end_line": len(lines) - 1, "label": ""}]
    return []


def assemble_email_manifest(
    *,
    subject: str | None,
    from_: str | None,
    to: list[str],
    cc: list[str],
    bcc: list[str],
    date: str | None,
    message_id: str | None,
    in_reply_to: str | None,
    has_html_body: bool,
    has_text_body: bool,
    quoted_ranges: list[dict[str, Any]],
    inline_images: list[dict[str, Any]],
    skipped_inline_images: int,
    blocked_remote_images: int,
    embedded_inline_images: int,
    attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the manifest ``email`` section shared by both renderers."""
    return {
        "subject": subject or None,
        "from": from_ or None,
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "date": date,
        "message_id": message_id or None,
        "in_reply_to": in_reply_to or None,
        "has_html_body": has_html_body,
        "has_text_body": has_text_body,
        "quoted_ranges": quoted_ranges,
        "inline_images": inline_images,
        "skipped_inline_images": skipped_inline_images,
        "blocked_remote_images": blocked_remote_images,
        "embedded_inline_images": embedded_inline_images,
        "attachments": attachments,
    }
