from __future__ import annotations

from pathlib import Path

from services.extraction.pptx_extractor import PptxExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_pptx_extractor_reads_text_from_pptx() -> None:
    extractor = PptxExtractor()
    text = extractor.extract(FIXTURES / "sample.pptx")

    assert "Hello PPTX World" in text
    assert "test document for extraction" in text


def test_pptx_extractor_returns_empty_for_missing_file() -> None:
    extractor = PptxExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.pptx")

    assert text == ""
