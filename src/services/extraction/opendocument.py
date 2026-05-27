"""OpenDocument Spreadsheet (ODS) and Presentation (ODP) extractors.

Both formats are ODF zip archives containing a ``content.xml`` file.
The approach mirrors :class:`~services.extraction.odt.OdtExtractor`:
iterate all elements and collect non-empty paragraph (``}p``) text nodes.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from services.extraction.base import ExtractionResult


def _extract_odf_text(path: Path) -> str:
    """Return joined paragraph text from an ODF zip archive."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "content.xml" not in zf.namelist():
                return ""
            xml = zf.read("content.xml").decode("utf-8")
        root = ET.fromstring(xml)
        texts: list[str] = []
        for elem in root.iter():
            if elem.tag.endswith("}p"):
                para_text = "".join(elem.itertext())
                if para_text:
                    texts.append(para_text)
        return "\n".join(texts)
    except (OSError, zipfile.BadZipFile, ET.ParseError, UnicodeDecodeError):
        return ""


class OdsExtractor:
    """Extract text from ODS (OpenDocument Spreadsheet) files."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return text from all paragraph nodes inside content.xml."""
        return ExtractionResult(text=_extract_odf_text(path))


class OdpExtractor:
    """Extract text from ODP (OpenDocument Presentation) files."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return text from all paragraph nodes inside content.xml."""
        return ExtractionResult(text=_extract_odf_text(path))
