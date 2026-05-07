"""Plain text file extractor."""

from __future__ import annotations

from pathlib import Path


class PlainExtractor:
    """Extract text from plain-text files (.txt, .md, .csv, etc.)."""

    def extract(self, path: Path) -> str:
        """Read the file as UTF-8 text."""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
