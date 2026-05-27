"""RTF text extractor."""

from __future__ import annotations

from pathlib import Path

from striprtf.striprtf import rtf_to_text

from services.extraction.base import ExtractionResult


class RtfExtractor:
    """Extract text from RTF files using striprtf.

    RTF control words are ASCII-safe, so the file can be decoded as
    latin-1 when UTF-8 fails (covers Windows-1252 / ISO-8859-1 content).
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return plain text with RTF control words stripped."""
        raw: str | None = None
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            pass
        except OSError:
            return ExtractionResult(text="")

        if raw is None:
            # Fallback: latin-1 never raises; valid for any RTF where the
            # extended bytes represent Windows-1252 / ISO-8859-1 text.
            try:
                raw = path.read_text(encoding="latin-1")
            except OSError:
                return ExtractionResult(text="")

        return ExtractionResult(text=rtf_to_text(raw))  # type: ignore[no-untyped-call]
