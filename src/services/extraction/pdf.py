"""PDF text extractor."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfStreamError


class PdfExtractor:
    """Extract text from PDF files using pypdf."""

    def extract(self, path: Path) -> str:
        """Return concatenated text from all pages."""
        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except (OSError, ValueError, PdfStreamError):
            return ""
