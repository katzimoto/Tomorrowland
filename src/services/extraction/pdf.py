"""PDF text extractor.

Extracts text via pypdf.  When pypdf returns empty text for a non-empty PDF
(i.e. the file is a scanned/image-based PDF) and ``ENABLE_OCR=true`` is set,
falls back to rendering each page with ``pdf2image`` and running Tesseract
OCR via ``pytesseract``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfStreamError

logger = logging.getLogger(__name__)


def _ocr_pdf(path: Path) -> str:
    """Render each PDF page as an image and OCR it.

    Returns an empty string when ``pdf2image`` or ``pytesseract`` are absent.
    """
    try:
        import pytesseract  # type: ignore[import-not-found]
        from pdf2image import convert_from_path  # type: ignore[import-not-found]
    except ImportError:
        return ""

    try:
        images = convert_from_path(str(path))
        parts = [pytesseract.image_to_string(img).strip() for img in images]
        return "\n".join(p for p in parts if p)
    except Exception:
        logger.debug("PDF OCR failed for path=%s", path, exc_info=True)
        return ""


class PdfExtractor:
    """Extract text from PDF files.

    Uses pypdf for native text extraction.  Falls back to OCR when pypdf
    returns no text and the ``ocr_fallback`` flag is enabled (controlled by
    ``Settings.ENABLE_OCR``).
    """

    def __init__(self, ocr_fallback: bool = False) -> None:
        self._ocr_fallback = ocr_fallback

    def extract(self, path: Path) -> str:
        """Return concatenated text from all pages."""
        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages)
        except (OSError, ValueError, PdfStreamError):
            return ""

        if text.strip():
            return text

        # Empty result on a non-empty PDF → likely scanned; try OCR if enabled.
        if self._ocr_fallback and reader.pages:
            logger.debug("pypdf returned empty text; attempting OCR for path=%s", path)
            return _ocr_pdf(path)

        return text
