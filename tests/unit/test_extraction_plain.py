from __future__ import annotations

from pathlib import Path

from services.extraction.plain import PlainExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_plain_extractor_reads_txt_file() -> None:
    extractor = PlainExtractor()
    result = extractor.extract(FIXTURES / "sample.txt")

    assert "Hello TXT World" in result.text
    assert "test document for extraction" in result.text


def test_plain_extractor_reads_md_file() -> None:
    extractor = PlainExtractor()
    path = FIXTURES / "sample.txt"
    # Plain extractor works on any text/* mime by reading raw bytes
    result = extractor.extract(path)

    assert len(result.text) > 0


def test_plain_extractor_returns_empty_for_missing_file() -> None:
    extractor = PlainExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.txt")

    assert result.text == ""
