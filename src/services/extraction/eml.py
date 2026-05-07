"""EML (email) text extractor."""

from __future__ import annotations

import email
from pathlib import Path


class EmlExtractor:
    """Extract text from .eml files including headers and body."""

    def extract(self, path: Path) -> str:
        """Return subject, from, to, and body text."""
        try:
            raw = path.read_bytes()
            msg = email.message_from_bytes(raw)
            texts: list[str] = []
            for header in ("Subject", "From", "To", "Date"):
                value = msg.get(header)
                if value:
                    texts.append(f"{header}: {value}")
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in {"text/plain", "text/html"}:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        texts.append(payload.decode("utf-8", errors="replace"))
            return "\n\n".join(texts)
        except (OSError, UnicodeDecodeError):
            return ""
