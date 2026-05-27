from __future__ import annotations

from pathlib import Path

from services.extraction.docx import DocxExtractor
from services.extraction.pdf import PdfExtractor
from services.extraction.plain import PlainExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_plain_extractor_returns_empty_for_empty_file() -> None:
    extractor = PlainExtractor()
    path = FIXTURES / "empty.txt"
    path.write_text("", encoding="utf-8")
    result = extractor.extract(path)
    path.unlink()

    assert result.text == ""


def test_pdf_extractor_returns_empty_for_corrupted_pdf() -> None:
    extractor = PdfExtractor()
    path = FIXTURES / "corrupted.pdf"
    path.write_text("this is not a pdf", encoding="utf-8")
    result = extractor.extract(path)
    path.unlink()

    assert result.text == ""


def test_docx_extractor_returns_empty_for_corrupted_docx() -> None:
    extractor = DocxExtractor()
    path = FIXTURES / "corrupted.docx"
    path.write_text("this is not a docx", encoding="utf-8")
    result = extractor.extract(path)
    path.unlink()

    assert result.text == ""
