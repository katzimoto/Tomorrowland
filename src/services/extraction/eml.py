"""EML (email) text extractor."""

from __future__ import annotations

import email
import mimetypes
from email import policy
from email.errors import MessageError
from email.header import decode_header
from html.parser import HTMLParser
from pathlib import Path

from services.extraction.base import AttachmentData, ExtractionResult


class EmlExtractor:
    """Extract text from .eml files including headers and body.

    A single walk over the parsed message collects body text, attachment
    metadata for search indexing, and the raw attachment bytes so the pipeline
    can create child documents — the message is parsed only once.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return a best-effort extraction of headers, body text, and attachments.

        The extractor attempts to:
        - Decode all headers (RFC2047) and include them in the output.
        - Extract ``text/plain`` parts and decode them.
        - Extract ``text/html`` parts and convert them to plain text.
        - List attachments with filename, content type, and size in bytes.

        ``ExtractionResult.attachments`` contains the raw bytes of each
        non-inline attachment so the pipeline can create child documents.
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
            attachment_lines: list[str] = []
            attachments: list[AttachmentData] = []

            for part in msg.walk():
                # Skip container/multipart nodes
                if part.is_multipart():
                    continue

                ctype = part.get_content_type()
                disposition = part.get_content_disposition()  # 'inline', 'attachment', or None
                filename = part.get_filename()
                raw_payload = part.get_payload(decode=True)

                if filename or disposition == "attachment":
                    if isinstance(raw_payload, (bytes, bytearray)) and raw_payload:
                        fname = filename or "(unknown)"
                        size = len(raw_payload)
                        attachment_lines.append(f"{fname} ({ctype}, {size} bytes)")
                        # Determine MIME type: prefer filename-derived type when
                        # the declared value is the RFC 2045 default "text/plain"
                        # and no explicit Content-Type header is present.
                        guessed = mimetypes.guess_type(fname)[0] or "application/octet-stream"
                        if ctype == "text/plain" and "Content-Type" not in part:
                            mime = guessed
                        else:
                            mime = ctype
                        actual_fname = filename or "attachment"
                        attachments.append(
                            AttachmentData(
                                filename=actual_fname,
                                mime_type=mime,
                                data=bytes(raw_payload),
                            )
                        )
                    continue

                # Decode payload for body text
                try:
                    payload = part.get_content()
                except (MessageError, KeyError):
                    if isinstance(raw_payload, bytes):
                        payload = raw_payload.decode(
                            part.get_content_charset("utf-8"), errors="replace"
                        )
                    else:
                        payload = raw_payload or ""

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
            if attachment_lines:
                sections.append("Attachments:\n" + "\n".join(attachment_lines))

            return ExtractionResult(text="\n\n".join(sections), attachments=attachments)
        except (OSError, UnicodeDecodeError):
            return ExtractionResult(text="")
        except Exception:
            # Be conservative: never raise during extraction
            return ExtractionResult(text="")
