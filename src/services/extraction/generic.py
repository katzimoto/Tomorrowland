"""Generic best-effort text extractor for files with no registered extractor."""

from __future__ import annotations

import logging
from pathlib import Path

from services.extraction.base import ExtractionResult

logger = logging.getLogger(__name__)


class GenericExtractor:
    """Extract text from any file that has no specific extractor registered.

    Identical to :class:`~services.extraction.plain.PlainExtractor` except
    it does **not** fall back to latin-1.  This prevents returning garbage
    bytes when the file is a true binary (image, executable, etc.) —
    charset-normalizer returns ``None`` for low-confidence binary content,
    so those files produce an empty string rather than mojibake.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return decoded text, or ``ExtractionResult(text="")`` if the file looks binary."""
        try:
            return ExtractionResult(text=path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            logger.debug("File is not valid UTF-8, trying charset detection: %s", path)
        except OSError:
            return ExtractionResult(text="")

        try:
            from charset_normalizer import from_path

            result = from_path(path).best()
            if result is not None:
                return ExtractionResult(text=str(result))
        except Exception:
            logger.debug("Charset detection failed for generic file: %s", path)

        # Do NOT fall back to latin-1 here — that would decode any binary
        # file and return garbage to the indexing pipeline.
        return ExtractionResult(text="")
