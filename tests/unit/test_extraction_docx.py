from __future__ import annotations

from pathlib import Path

from services.extraction.docx import DocxExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_docx_extractor_reads_text_from_docx() -> None:
    extractor = DocxExtractor()
    text = extractor.extract(FIXTURES / "sample.docx")

    assert "Hello DOCX World" in text
    assert "test document for extraction" in text


def test_docx_extractor_returns_empty_for_missing_file() -> None:
    extractor = DocxExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.docx")

    assert text == ""
