"""Plain text file extractor."""

from __future__ import annotations

from pathlib import Path


class PlainExtractor:
    """Extract text from plain-text files (.txt, .md, .csv, etc.).

    Attempts UTF-8 first, then falls back to charset-normalizer detection,
    and finally to latin-1 (which never raises a decode error) so that
    non-UTF-8 documents are still readable rather than silently empty.
    """

    def extract(self, path: Path) -> str:
        """Read the file, trying multiple encodings."""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            pass
        except OSError:
            return ""

        # Second pass: detect encoding via charset-normalizer.
        try:
            from charset_normalizer import from_path  # type: ignore[import-not-found]

            result = from_path(path).best()
            if result is not None:
                return str(result)
        except Exception:
            pass

        # Final fallback: latin-1 never raises on binary input.
        try:
            return path.read_text(encoding="latin-1")
        except OSError:
            return ""
