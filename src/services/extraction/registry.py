"""Extractor registry mapping MIME types to extractors."""

from __future__ import annotations

from pathlib import Path

from services.extraction.base import Extractor
from services.extraction.docx import DocxExtractor
from services.extraction.pdf import PdfExtractor
from services.extraction.plain import PlainExtractor
from services.extraction.pptx_extractor import PptxExtractor
from services.extraction.xlsx import XlsxExtractor


class ExtractorRegistry:
    """Map MIME types to concrete extractors."""

    def __init__(self) -> None:
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        pptx_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        self._extractors: dict[str, Extractor] = {
            "text/plain": PlainExtractor(),
            "text/markdown": PlainExtractor(),
            "text/csv": PlainExtractor(),
            "application/pdf": PdfExtractor(),
            docx_mime: DocxExtractor(),
            pptx_mime: PptxExtractor(),
            xlsx_mime: XlsxExtractor(),
        }

    def register(self, mime_type: str, extractor: Extractor) -> None:
        """Add or override an extractor for a MIME type."""
        self._extractors[mime_type] = extractor

    def get(self, mime_type: str) -> Extractor | None:
        """Return the extractor for *mime_type* when registered."""
        return self._extractors.get(mime_type)

    def extract(self, path: Path, mime_type: str) -> str:
        """Extract text from *path* using the extractor for *mime_type*.

        Returns an empty string when the MIME type is unknown or extraction
        fails.
        """
        extractor = self.get(mime_type)
        if extractor is None:
            return ""
        return extractor.extract(path)
