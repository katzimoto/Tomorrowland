from __future__ import annotations

from pathlib import Path

from services.extraction.xlsx import XlsxExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_xlsx_extractor_reads_text_from_xlsx() -> None:
    extractor = XlsxExtractor()
    text = extractor.extract(FIXTURES / "sample.xlsx")

    assert "Hello" in text
    assert "Excel" in text
    assert "World" in text
    assert "test document for extraction" in text


def test_xlsx_extractor_returns_empty_for_missing_file() -> None:
    extractor = XlsxExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.xlsx")

    assert text == ""
