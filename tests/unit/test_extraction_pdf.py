from __future__ import annotations

from pathlib import Path

from services.extraction.pdf import PdfExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_pdf_extractor_reads_text_from_pdf() -> None:
    extractor = PdfExtractor()
    text = extractor.extract(FIXTURES / "sample.pdf")

    assert "Hello PDF World" in text
    assert "test document for extraction" in text


def test_pdf_extractor_returns_empty_for_missing_file() -> None:
    extractor = PdfExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.pdf")

    assert text == ""
