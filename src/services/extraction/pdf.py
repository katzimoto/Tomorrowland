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
from pypdf.errors import FileNotDecryptedError, PdfStreamError

from services.extraction.base import ExtractionResult, LocationSegment

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

    def extract(self, path: Path) -> ExtractionResult:
        """Return concatenated text from all pages with page-number segments."""
        try:
            reader = PdfReader(str(path))
        except (OSError, ValueError, PdfStreamError, FileNotDecryptedError) as exc:
            logger.debug("PDF reader failed for path=%s: %s", path, exc)
            return ExtractionResult(text="")

        pages_text: list[str] = []
        segments: list[LocationSegment] = []
        offset = 0
        # Accessing reader.pages lazily raises on an undecryptable (encrypted)
        # PDF; treat it as empty rather than letting it propagate.
        try:
            len(reader.pages)
        except (FileNotDecryptedError, PdfStreamError, ValueError) as exc:
            logger.debug("PDF pages unavailable for path=%s: %s", path, exc)
            return ExtractionResult(text="")
        for i, page in enumerate(reader.pages, 1):
            try:
                page_text = page.extract_text() or ""
            except (OSError, ValueError, PdfStreamError, FileNotDecryptedError) as exc:
                logger.debug(
                    "PDF page %d extraction failed for path=%s: %s; continuing",
                    i,
                    path,
                    exc,
                )
                page_text = ""
            if page_text:
                pages_text.append(page_text)
                end = offset + len(page_text)
                segments.append(
                    LocationSegment(
                        start_char=offset,
                        end_char=end,
                        page_number=i,
                    )
                )
                offset = end + 1  # +1 for the newline separator
        text = "\n".join(pages_text)

        if text.strip():
            return ExtractionResult(text=text, location_segments=segments)

        # Empty result on a non-empty PDF → likely scanned; try OCR if enabled.
        if self._ocr_fallback and reader.pages:
            logger.debug("pypdf returned empty text; attempting OCR for path=%s", path)
            ocr_text = _ocr_pdf(path)
            return ExtractionResult(text=ocr_text)

        return ExtractionResult(text=text)
