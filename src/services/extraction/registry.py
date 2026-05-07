"""Extractor registry mapping MIME types to extractors."""

from __future__ import annotations

from pathlib import Path

from services.extraction.base import Extractor
from services.extraction.docx import DocxExtractor
from services.extraction.eml import EmlExtractor
from services.extraction.html import HtmlExtractor
from services.extraction.json_extractor import JsonExtractor
from services.extraction.odt import OdtExtractor
from services.extraction.pdf import PdfExtractor
from services.extraction.plain import PlainExtractor
from services.extraction.pptx_extractor import PptxExtractor
from services.extraction.xlsx import XlsxExtractor
from services.extraction.xml_extractor import XmlExtractor

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExtractorRegistry:
    """Map MIME types to concrete extractors."""

    def __init__(self) -> None:
        self._extractors: dict[str, Extractor] = {
            # Plain text family
            "text/plain": PlainExtractor(),
            "text/markdown": PlainExtractor(),
            "text/csv": PlainExtractor(),
            "text/html": HtmlExtractor(),
            "text/xml": XmlExtractor(),
            "application/json": JsonExtractor(),
            "application/xml": XmlExtractor(),
            # PDF
            "application/pdf": PdfExtractor(),
            # Microsoft Office
            _DOCX_MIME: DocxExtractor(),
            _PPTX_MIME: PptxExtractor(),
            _XLSX_MIME: XlsxExtractor(),
            # OpenDocument
            "application/vnd.oasis.opendocument.text": OdtExtractor(),
            # Email
            "message/rfc822": EmlExtractor(),
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
