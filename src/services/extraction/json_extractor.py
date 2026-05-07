"""JSON text extractor."""

from __future__ import annotations

from pathlib import Path


class JsonExtractor:
    """Extract raw text from JSON files for indexing."""

    def extract(self, path: Path) -> str:
        """Read the file as UTF-8 text."""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
