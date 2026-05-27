"""XML text extractor."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from services.extraction.base import ExtractionResult


class XmlExtractor:
    """Extract plain text from XML files for indexing and translation.

    Uses ``xml.etree.ElementTree`` so that:

    * XML tags are stripped — translators only see human-readable text.
    * The encoding declared in the XML prolog (``<?xml … encoding="…"?>``)
      is respected automatically, so ISO-8859-1, Windows-1251, etc. all
      work without a manual fallback chain.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return all text nodes joined by newlines, with tags stripped."""
        try:
            tree = ET.parse(str(path))  # noqa: S314 — local files only
            root = tree.getroot()
            parts = [t.strip() for t in root.itertext() if t and t.strip()]
            return ExtractionResult(text="\n".join(parts))
        except (OSError, ET.ParseError):
            return ExtractionResult(text="")
