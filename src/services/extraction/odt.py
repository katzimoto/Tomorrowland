"""ODT (OpenDocument Text) extractor."""

from __future__ import annotations

from pathlib import Path

from services.extraction.base import ExtractionResult
from services.extraction.opendocument import _extract_odf_text


class OdtExtractor:
    """Extract text from ODT files using the embedded content.xml."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return text from all paragraph nodes inside content.xml."""
        return ExtractionResult(text=_extract_odf_text(path))
