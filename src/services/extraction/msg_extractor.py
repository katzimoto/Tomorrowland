"""MSG (Outlook) text extractor."""

from __future__ import annotations

import logging
import mimetypes
from contextlib import suppress
from html.parser import HTMLParser
from pathlib import Path

import extract_msg

from services.extraction.base import AttachmentData, ExtractionResult

logger = logging.getLogger(__name__)


class MsgExtractor:
    """Extract text from Outlook .msg files using extract-msg.

    The message is opened once: body text, attachment metadata for search
    indexing, and the raw attachment bytes are all collected in a single
    pass so the pipeline can create child documents without re-opening the
    file.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return subject, sender, body, attachment metadata, and attachment bytes.

        Best-effort extractor that:
        - Safely reads common header fields.
        - Includes plain text and converts HTML bodies to text.
        - Lists attachments with name, content type, and size.

        ``ExtractionResult.attachments`` contains the raw bytes of each
        attachment so the pipeline can create child documents.
        """
        try:
            msg = extract_msg.Message(str(path))  # type: ignore[no-untyped-call]
        except Exception:
            logger.warning("Failed to open MSG file path=%s", path, exc_info=True)
            return ExtractionResult(text="")
        try:

            def _safe_str(val: object | None) -> str:
                if val is None:
                    return ""
                if isinstance(val, bytes):
                    return val.decode("utf-8", errors="replace")
                return str(val)

            class _HTMLToText(HTMLParser):
                def __init__(self) -> None:
                    super().__init__(convert_charrefs=True)
                    self._parts: list[str] = []

                def handle_data(self, data: str) -> None:
                    self._parts.append(data)

                def get_text(self) -> str:
                    return "".join(self._parts)

            headers: list[str] = []
            subj = _safe_str(getattr(msg, "subject", None))
            if subj:
                headers.append(f"Subject: {subj}")
            sender = _safe_str(getattr(msg, "sender", None))
            if sender:
                headers.append(f"From: {sender}")
            to = _safe_str(getattr(msg, "to", None))
            if to:
                headers.append(f"To: {to}")
            date = _safe_str(getattr(msg, "date", None))
            if date:
                headers.append(f"Date: {date}")

            body_parts: list[str] = []
            # Plain text body
            body = getattr(msg, "body", None)
            if body:
                body_parts.append(_safe_str(body))

            # Try HTML body variants, if present
            html_body = getattr(msg, "htmlBody", None) or getattr(msg, "html", None)
            if html_body:
                html_text = _safe_str(html_body)
                parser = _HTMLToText()
                parser.feed(html_text)
                body_parts.append(parser.get_text())

            # Single pass over attachments: collect metadata for text + raw bytes for pipeline
            attachment_lines: list[str] = []
            attachments: list[AttachmentData] = []
            for att in getattr(msg, "attachments", []) or []:
                name = (
                    getattr(att, "longFilename", None)
                    or getattr(att, "filename", None)
                    or getattr(att, "shortFilename", None)
                    or getattr(att, "name", None)
                    or "(unknown)"
                )
                raw = (
                    getattr(att, "data", None)
                    or getattr(att, "data_obj", None)
                    or getattr(att, "payload", None)
                )
                ctype = (
                    getattr(att, "content_type", None)
                    or getattr(att, "mime_type", None)
                    or "application/octet-stream"
                )
                size = 0
                if isinstance(raw, (bytes, bytearray)):
                    size = len(raw)
                elif raw is not None and hasattr(raw, "read"):
                    try:
                        pos = raw.tell()
                        raw.seek(0, 2)
                        size = raw.tell()
                        raw.seek(pos)
                    except Exception:
                        size = 0
                attachment_lines.append(f"{name} ({ctype}, {size} bytes)")

                # Collect raw bytes for child-document creation
                if isinstance(raw, (bytes, bytearray)) and raw:
                    fname = (
                        getattr(att, "longFilename", None)
                        or getattr(att, "filename", None)
                        or getattr(att, "shortFilename", None)
                        or getattr(att, "name", None)
                        or "attachment"
                    )
                    resolved_ctype = (
                        getattr(att, "content_type", None)
                        or getattr(att, "mime_type", None)
                        or mimetypes.guess_type(fname)[0]
                        or "application/octet-stream"
                    )
                    attachments.append(
                        AttachmentData(filename=fname, mime_type=resolved_ctype, data=bytes(raw))
                    )

            sections: list[str] = []
            if headers:
                sections.append("Headers:\n" + "\n".join(headers))
            if body_parts:
                sections.append("Body:\n" + "\n\n".join(body_parts))
            if attachment_lines:
                sections.append("Attachments:\n" + "\n".join(attachment_lines))

            return ExtractionResult(text="\n\n".join(sections), attachments=attachments)
        except Exception:
            logger.warning("Failed to extract MSG content path=%s", path, exc_info=True)
            return ExtractionResult(text="")
        finally:
            with suppress(Exception):
                msg.close()
