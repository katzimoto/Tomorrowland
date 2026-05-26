"""EML (email) text extractor."""

from __future__ import annotations

import email
import mimetypes
from email import policy
from email.errors import MessageError
from email.header import decode_header
from html.parser import HTMLParser
from pathlib import Path

from services.extraction.base import AttachmentData


class EmlExtractor:
    """Extract text from .eml files including headers and body."""

    def extract(self, path: Path) -> str:
        """Return a best-effort extraction of headers, body text, and attachments.

        The extractor attempts to:
        - Decode all headers (RFC2047) and include them in the output.
        - Extract `text/plain` parts and decode them.
        - Extract `text/html` parts and convert them to plain text.
        - List attachments with filename, content type, and size in bytes.
        """
        try:
            raw = path.read_bytes()
            msg = email.message_from_bytes(raw, policy=policy.default)

            def _decode_header(value: str | None) -> str:
                if not value:
                    return ""
                try:
                    parts = decode_header(value)
                    decoded = []
                    for fragment, enc in parts:
                        if isinstance(fragment, bytes):
                            decoded.append(fragment.decode(enc or "utf-8", errors="replace"))
                        else:
                            decoded.append(fragment)
                    return "".join(decoded)
                except Exception:
                    return str(value)

            class _HTMLToText(HTMLParser):
                def __init__(self) -> None:
                    super().__init__(convert_charrefs=True)
                    self._parts: list[str] = []

                def handle_data(self, data: str) -> None:
                    self._parts.append(data)

                def get_text(self) -> str:
                    return "".join(self._parts)

            headers: list[str] = []
            for name, value in msg.items():
                headers.append(f"{name}: {_decode_header(value)}")

            body_parts: list[str] = []
            attachments: list[str] = []

            for part in msg.walk():
                # Skip container/multipart nodes
                if part.is_multipart():
                    continue

                ctype = part.get_content_type()
                disposition = part.get_content_disposition()  # 'inline', 'attachment', or None
                filename = part.get_filename()

                try:
                    payload = part.get_content()
                except (MessageError, KeyError):
                    # Fallback to raw payload decode
                    raw_payload = part.get_payload(decode=True)
                    if isinstance(raw_payload, bytes):
                        payload = raw_payload.decode(
                            part.get_content_charset("utf-8"), errors="replace"
                        )
                    else:
                        payload = raw_payload or ""

                if filename or disposition == "attachment":
                    raw_bytes = part.get_payload(decode=True) or b""
                    size = len(raw_bytes) if isinstance(raw_bytes, (bytes, bytearray)) else 0
                    fname = filename or "(unknown)"
                    attachments.append(f"{fname} ({ctype}, {size} bytes)")
                    continue

                if ctype == "text/plain":
                    if isinstance(payload, str):
                        body_parts.append(payload)
                    elif isinstance(payload, (bytes, bytearray)):
                        body_parts.append(
                            payload.decode(part.get_content_charset("utf-8"), errors="replace")
                        )
                elif ctype == "text/html":
                    html_text = ""
                    if isinstance(payload, str):
                        html_text = payload
                    elif isinstance(payload, (bytes, bytearray)):
                        html_text = payload.decode(
                            part.get_content_charset("utf-8"), errors="replace"
                        )
                    parser = _HTMLToText()
                    parser.feed(html_text)
                    body_parts.append(parser.get_text())

            sections: list[str] = []
            if headers:
                sections.append("Headers:\n" + "\n".join(headers))
            if body_parts:
                sections.append("Body:\n" + "\n\n".join(body_parts))
            if attachments:
                sections.append("Attachments:\n" + "\n".join(attachments))

            return "\n\n".join(sections)
        except (OSError, UnicodeDecodeError):
            return ""
        except Exception:
            # Be conservative: never raise during extraction
            return ""

    def extract_attachments(self, path: Path) -> list[AttachmentData]:
        """Return raw bytes for each non-inline attachment in the EML file."""
        try:
            raw = path.read_bytes()
            msg = email.message_from_bytes(raw, policy=policy.default)
            result: list[AttachmentData] = []
            for part in msg.walk():
                if part.is_multipart():
                    continue
                filename = part.get_filename()
                disposition = part.get_content_disposition()
                if not (filename or disposition == "attachment"):
                    continue
                data = part.get_payload(decode=True)
                if not isinstance(data, (bytes, bytearray)) or not data:
                    continue
                fname = filename or "attachment"
                declared_ctype = part.get_content_type()  # never None with policy.default
                guessed = mimetypes.guess_type(fname)[0] or "application/octet-stream"
                # email.policy.default returns the RFC 2045 default "text/plain"
                # when no Content-Type header is present.  Prefer the filename-
                # derived MIME type when the declared value is just that default,
                # so a PDF named "report.pdf" without an explicit Content-Type
                # header is typed as "application/pdf" rather than "text/plain".
                if declared_ctype == "text/plain" and "Content-Type" not in part:
                    mime = guessed
                else:
                    mime = declared_ctype
                result.append(AttachmentData(filename=fname, mime_type=mime, data=bytes(data)))
            return result
        except Exception:
            return []
