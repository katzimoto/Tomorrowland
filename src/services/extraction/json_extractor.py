"""JSON text extractor."""

from __future__ import annotations

from pathlib import Path

from services.extraction.base import ExtractionResult


class JsonExtractor:
    """Extract raw text from JSON files for indexing."""

    def extract(self, path: Path) -> ExtractionResult:
        """Read the file as UTF-8 text."""
        try:
            return ExtractionResult(text=path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return ExtractionResult(text="")
