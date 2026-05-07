"""XML text extractor."""

from __future__ import annotations

from pathlib import Path


class XmlExtractor:
    """Extract raw text from XML files for indexing."""

    def extract(self, path: Path) -> str:
        """Read the file as UTF-8 text."""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
