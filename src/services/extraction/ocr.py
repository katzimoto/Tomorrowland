"""OCR extractor for raster image files using Tesseract.

Requires ``pytesseract`` and ``Pillow`` at runtime.  When either is absent
the extractor returns an empty string rather than raising, so the pipeline
degrades gracefully when Tesseract is not installed.

Enabled for image/* MIME types registered in :mod:`services.extraction.registry`
only when ``ENABLE_OCR=true`` is set in the environment / ``.env`` file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from services.extraction.base import ExtractionResult

logger = logging.getLogger(__name__)


class OcrExtractor:
    """Extract text from raster images via Tesseract OCR."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return OCR'd text from an image file.

        Returns an empty ExtractionResult when Tesseract or Pillow are
        unavailable or when the file cannot be opened.
        """
        try:
            import pytesseract  # type: ignore[import-not-found]
            from PIL import Image  # type: ignore[import-untyped]
        except ImportError:
            logger.debug("pytesseract / Pillow not installed; OCR unavailable")
            return ExtractionResult(text="")

        try:
            image = Image.open(path)
            result: str = pytesseract.image_to_string(image)
            return ExtractionResult(text=result.strip())
        except Exception:
            logger.debug("OCR failed for path=%s", path, exc_info=True)
            return ExtractionResult(text="")
