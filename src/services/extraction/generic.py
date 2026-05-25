"""Generic best-effort text extractor for files with no registered extractor."""

from __future__ import annotations

from pathlib import Path


class GenericExtractor:
    """Extract text from any file that has no specific extractor registered.

    Identical to :class:`~services.extraction.plain.PlainExtractor` except
    it does **not** fall back to latin-1.  This prevents returning garbage
    bytes when the file is a true binary (image, executable, etc.) —
    charset-normalizer returns ``None`` for low-confidence binary content,
    so those files produce an empty string rather than mojibake.
    """

    def extract(self, path: Path) -> str:
        """Return decoded text, or ``""`` if the file looks binary."""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            pass
        except OSError:
            return ""

        try:
            from charset_normalizer import from_path  # type: ignore[import-not-found]

            result = from_path(path).best()
            if result is not None:
                return str(result)
        except Exception:
            pass

        # Do NOT fall back to latin-1 here — that would decode any binary
        # file and return garbage to the indexing pipeline.
        return ""
