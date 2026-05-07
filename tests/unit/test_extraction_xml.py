from __future__ import annotations

from pathlib import Path

from services.extraction.xml_extractor import XmlExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_xml_extractor_reads_raw_xml() -> None:
    extractor = XmlExtractor()
    path = FIXTURES / "sample.xml"
    path.write_text("<root><item>Hello XML</item></root>", encoding="utf-8")
    text = extractor.extract(path)
    path.unlink()

    assert "Hello XML" in text


def test_xml_extractor_returns_empty_for_missing_file() -> None:
    extractor = XmlExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.xml")

    assert text == ""
