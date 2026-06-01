"""Plain text file extractor."""

from __future__ import annotations

import logging
from pathlib import Path

from services.extraction.base import ExtractionResult

logger = logging.getLogger(__name__)


class PlainExtractor:
    """Extract text from plain-text files (.txt, .md, .csv, etc.).

    Attempts UTF-8 first, then falls back to charset-normalizer detection,
    and finally to latin-1 (which never raises a decode error) so that
    non-UTF-8 documents are still readable rather than silently empty.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Read the file, trying multiple encodings."""
        try:
            return ExtractionResult(text=path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            logger.debug("Plain file is not valid UTF-8, trying charset detection: %s", path)
        except OSError:
            return ExtractionResult(text="")

        # Second pass: detect encoding via charset-normalizer.
        try:
            from charset_normalizer import from_path

            result = from_path(path).best()
            if result is not None:
                return ExtractionResult(text=str(result))
        except Exception:
            logger.debug("Charset detection failed, falling back to latin-1: %s", path)

        # Final fallback: latin-1 never raises on binary input.
        try:
            return ExtractionResult(text=path.read_text(encoding="latin-1"))
        except OSError:
            return ExtractionResult(text="")
