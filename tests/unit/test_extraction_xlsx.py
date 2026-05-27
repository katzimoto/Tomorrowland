from __future__ import annotations

from pathlib import Path

from services.extraction.xlsx import XlsxExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_xlsx_extractor_reads_text_from_xlsx() -> None:
    extractor = XlsxExtractor()
    result = extractor.extract(FIXTURES / "sample.xlsx")

    assert "Hello" in result.text
    assert "Excel" in result.text
    assert "World" in result.text
    assert "test document for extraction" in result.text


def test_xlsx_extractor_returns_empty_for_missing_file() -> None:
    extractor = XlsxExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.xlsx")

    assert result.text == ""
