from __future__ import annotations

from pathlib import Path

from services.extraction.xls import XlsExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_xls_extractor_reads_text() -> None:
    extractor = XlsExtractor()
    result = extractor.extract(FIXTURES / "sample.xls")

    assert "Hello" in result.text
    assert "Excel" in result.text
    assert "World" in result.text
    assert "test document for extraction" in result.text


def test_xls_extractor_formats_integers_without_decimal() -> None:
    """Whole-number cells should appear as ints, not floats (42 not 42.0)."""
    extractor = XlsExtractor()
    result = extractor.extract(FIXTURES / "sample.xls")

    assert "42" in result.text
    assert "42.0" not in result.text


def test_xls_extractor_returns_empty_for_missing_file() -> None:
    extractor = XlsExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.xls")

    assert result.text == ""


def test_xls_extractor_returns_empty_for_corrupt_file(tmp_path: Path) -> None:
    corrupt = tmp_path / "bad.xls"
    corrupt.write_bytes(b"\x00\x01\x02\x03")
    extractor = XlsExtractor()
    assert extractor.extract(corrupt).text == ""
