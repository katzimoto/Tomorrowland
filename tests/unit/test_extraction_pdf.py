from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.pdf import PdfExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_pdf_extractor_reads_text_from_pdf() -> None:
    extractor = PdfExtractor()
    result = extractor.extract(FIXTURES / "sample.pdf")

    assert "Hello PDF World" in result.text
    assert "test document for extraction" in result.text


def test_pdf_extractor_returns_empty_for_missing_file() -> None:
    extractor = PdfExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.pdf")

    assert result.text == ""


def test_pdf_extractor_returns_location_segments() -> None:
    """PdfExtractor should emit one LocationSegment per page with page_number."""
    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "Page one content."
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = "Page two content."
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page_1, mock_page_2]

    with patch("services.extraction.pdf.PdfReader", return_value=mock_reader):
        result = PdfExtractor().extract(Path("/fake/path.pdf"))

    assert result.text == "Page one content.\nPage two content."
    assert len(result.location_segments) == 2
    assert result.location_segments[0].page_number == 1
    assert result.location_segments[0].start_char == 0
    assert result.location_segments[0].end_char == 17
    assert result.location_segments[1].page_number == 2
    assert result.location_segments[1].start_char == 18
    assert result.location_segments[1].end_char == 35


def test_pdf_extractor_empty_page_skips_segment(tmp_path: Path) -> None:
    """Empty pages should not produce a location segment."""
    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "Content."
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = ""
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page_1, mock_page_2]

    with patch("services.extraction.pdf.PdfReader", return_value=mock_reader):
        result = PdfExtractor().extract(Path("/fake/path.pdf"))

    assert result.text == "Content."
    assert len(result.location_segments) == 1
    assert result.location_segments[0].page_number == 1
