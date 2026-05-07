from __future__ import annotations

import zipfile
from pathlib import Path

from services.extraction.odt import OdtExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_odt_extractor_reads_text_from_odt() -> None:
    extractor = OdtExtractor()
    path = FIXTURES / "sample.odt"
    # Build a minimal ODT with content.xml
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "content.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<office:document-content "
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            "<text:p>Hello ODT</text:p>"
            "<text:p>test document for extraction</text:p>"
            "</office:document-content>",
        )
    text = extractor.extract(path)
    path.unlink()

    assert "Hello ODT" in text
    assert "test document for extraction" in text


def test_odt_extractor_returns_empty_for_missing_file() -> None:
    extractor = OdtExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.odt")

    assert text == ""


def test_odt_extractor_returns_empty_for_invalid_zip() -> None:
    extractor = OdtExtractor()
    path = FIXTURES / "not_an_odt.odt"
    path.write_text("this is not a zip file", encoding="utf-8")
    text = extractor.extract(path)
    path.unlink()

    assert text == ""
