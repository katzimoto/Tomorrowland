"""MSG (Outlook) text extractor."""

from __future__ import annotations

import mimetypes
from contextlib import suppress
from html.parser import HTMLParser
from pathlib import Path

import extract_msg

from services.extraction.base import AttachmentData


class MsgExtractor:
    """Extract text from Outlook .msg files using extract-msg."""

    def extract(self, path: Path) -> str:
        """Return subject, sender, body, and attachment metadata.

        Best-effort extractor that:
        - Safely reads common header fields.
        - Includes plain text and converts HTML bodies to text.
        - Lists attachments with name, content type, and size.
        """
        try:
            msg = extract_msg.Message(str(path))  # type: ignore[no-untyped-call]
        except Exception:
            return ""
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

            attachments: list[str] = []
            for att in getattr(msg, "attachments", []) or []:
                name = (
                    getattr(att, "longFilename", None)
                    or getattr(att, "filename", None)
                    or getattr(att, "shortFilename", None)
                    or getattr(att, "name", None)
                    or "(unknown)"
                )
                # Try common places for raw bytes
                raw = (
                    getattr(att, "data", None)
                    or getattr(att, "data_obj", None)
                    or getattr(att, "payload", None)
                )
                size = 0
                try:
                    if isinstance(raw, (bytes, bytearray)):
                        size = len(raw)
                    elif raw is not None and hasattr(raw, "read"):
                        pos = raw.tell()
                        raw.seek(0, 2)
                        size = raw.tell()
                        raw.seek(pos)
                except Exception:
                    size = 0
                ctype = (
                    getattr(att, "content_type", None)
                    or getattr(att, "mime_type", None)
                    or "application/octet-stream"
                )
                attachments.append(f"{name} ({ctype}, {size} bytes)")

            sections: list[str] = []
            if headers:
                sections.append("Headers:\n" + "\n".join(headers))
            if body_parts:
                sections.append("Body:\n" + "\n\n".join(body_parts))
            if attachments:
                sections.append("Attachments:\n" + "\n".join(attachments))

            return "\n\n".join(sections)
        except Exception:
            return ""
        finally:
            with suppress(Exception):
                msg.close()

    def extract_attachments(self, path: Path) -> list[AttachmentData]:
        """Return raw bytes for each attachment in the MSG file."""
        try:
            msg = extract_msg.Message(str(path))  # type: ignore[no-untyped-call]
        except Exception:
            return []
        try:
            result: list[AttachmentData] = []
            for att in getattr(msg, "attachments", []) or []:
                fname = (
                    getattr(att, "longFilename", None)
                    or getattr(att, "filename", None)
                    or getattr(att, "shortFilename", None)
                    or getattr(att, "name", None)
                    or "attachment"
                )
                raw = (
                    getattr(att, "data", None)
                    or getattr(att, "data_obj", None)
                    or getattr(att, "payload", None)
                )
                if not isinstance(raw, (bytes, bytearray)) or not raw:
                    continue
                ctype = (
                    getattr(att, "content_type", None)
                    or getattr(att, "mime_type", None)
                    or mimetypes.guess_type(fname)[0]
                    or "application/octet-stream"
                )
                result.append(AttachmentData(filename=fname, mime_type=ctype, data=bytes(raw)))
            return result
        except Exception:
            return []
        finally:
            with suppress(Exception):
                msg.close()
