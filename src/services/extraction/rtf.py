"""RTF text extractor."""

from __future__ import annotations

from pathlib import Path

from striprtf.striprtf import rtf_to_text


class RtfExtractor:
    """Extract text from RTF files using striprtf."""

    def extract(self, path: Path) -> str:
        """Return plain text with RTF control words stripped."""
        try:
            raw = path.read_text(encoding="utf-8")
            return rtf_to_text(raw)  # type: ignore[no-untyped-call, no-any-return]
        except (OSError, UnicodeDecodeError):
            return ""
