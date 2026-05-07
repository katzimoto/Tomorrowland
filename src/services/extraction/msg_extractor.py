"""MSG (Outlook) text extractor."""

from __future__ import annotations

from pathlib import Path

import extract_msg


class MsgExtractor:
    """Extract text from Outlook .msg files using extract-msg."""

    def extract(self, path: Path) -> str:
        """Return subject, sender, body, and attachment names."""
        try:
            msg = extract_msg.Message(str(path))  # type: ignore[no-untyped-call]
            texts: list[str] = []
            if msg.subject:
                texts.append(f"Subject: {msg.subject}")
            if msg.sender:
                texts.append(f"From: {msg.sender}")
            if msg.to:
                texts.append(f"To: {msg.to}")
            if msg.body:
                texts.append(msg.body)
            for att in msg.attachments:
                texts.append(f"Attachment: {att.name}")
            return "\n\n".join(texts)
        except (OSError, ValueError, RuntimeError):
            return ""
