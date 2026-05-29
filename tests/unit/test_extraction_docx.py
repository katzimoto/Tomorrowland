from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.docx import DocxExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_docx_extractor_reads_text_from_docx() -> None:
    extractor = DocxExtractor()
    result = extractor.extract(FIXTURES / "sample.docx")

    assert "Hello DOCX World" in result.text
    assert "test document for extraction" in result.text


def test_docx_extractor_returns_empty_for_missing_file() -> None:
    extractor = DocxExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.docx")

    assert result.text == ""


def test_docx_extractor_returns_empty_for_bad_zip(tmp_path: Path) -> None:
    """zipfile.BadZipFile from a truncated DOCX must return '' not propagate."""
    p = tmp_path / "bad.docx"
    p.write_bytes(b"PK\x03\x04truncated")
    with patch("services.extraction.docx.Document", side_effect=zipfile.BadZipFile("bad zip")):
        result = DocxExtractor().extract(p)
    assert result.text == ""


def test_docx_extractor_returns_empty_for_value_error(tmp_path: Path) -> None:
    """ValueError from python-docx must return '' not propagate."""
    p = tmp_path / "bad.docx"
    p.write_bytes(b"not a docx")
    with patch("services.extraction.docx.Document", side_effect=ValueError("invalid file")):
        result = DocxExtractor().extract(p)
    assert result.text == ""


def test_docx_extractor_returns_heading_segments() -> None:
    """DocxExtractor should emit LocationSegments for heading-style paragraphs."""

    def _mock_paragraph(text: str, is_heading: bool = False) -> MagicMock:
        p = MagicMock()
        p.text = text
        p.style.name = "Heading 1" if is_heading else "Normal"
        return p

    mock_doc = MagicMock()
    mock_doc.paragraphs = [
        _mock_paragraph("Intro paragraph."),
        _mock_paragraph("Chapter 1", is_heading=True),
        _mock_paragraph("Content under chapter one."),
        _mock_paragraph("Chapter 2", is_heading=True),
        _mock_paragraph("Content under chapter two."),
    ]
    mock_doc.tables = []

    with patch("services.extraction.docx.Document", return_value=mock_doc):
        result = DocxExtractor().extract(Path("/fake.docx"))

    assert "Intro paragraph." in result.text
    assert "Chapter 1" in result.text
    assert "Content under chapter one." in result.text
    assert "Chapter 2" in result.text

    # Should have segments for headings and content under headings
    heading_segs = [s for s in result.location_segments if s.section_heading == "Chapter 1"]
    assert len(heading_segs) >= 1, "Should have at least one segment with heading 'Chapter 1'"


def test_docx_extractor_no_headings_yields_empty_segments() -> None:
    """Docx without heading styles should return no location segments."""
    mock_doc = MagicMock()
    mock_p = MagicMock()
    mock_p.text = "Plain paragraph."
    mock_p.style.name = "Normal"
    mock_doc.paragraphs = [mock_p]
    mock_doc.tables = []

    with patch("services.extraction.docx.Document", return_value=mock_doc):
        result = DocxExtractor().extract(Path("/fake.docx"))

    assert result.location_segments == []
