"""ODT (OpenDocument Text) extractor."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from services.extraction.base import ExtractionResult


class OdtExtractor:
    """Extract text from ODT files using the embedded content.xml."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return text from all paragraph nodes inside content.xml."""
        try:
            with zipfile.ZipFile(path, "r") as zf:
                if "content.xml" not in zf.namelist():
                    return ExtractionResult(text="")
                xml = zf.read("content.xml").decode("utf-8")
            root = ET.fromstring(xml)
            texts: list[str] = []
            for elem in root.iter():
                if elem.tag.endswith("}p"):
                    para_text = "".join(elem.itertext())
                    if para_text:
                        texts.append(para_text)
            return ExtractionResult(text="\n".join(texts))
        except (OSError, zipfile.BadZipFile, ET.ParseError, UnicodeDecodeError):
            return ExtractionResult(text="")
