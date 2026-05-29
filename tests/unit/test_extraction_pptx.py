from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.pptx_extractor import PptxExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_pptx_extractor_reads_text_from_pptx() -> None:
    extractor = PptxExtractor()
    result = extractor.extract(FIXTURES / "sample.pptx")

    assert "Hello PPTX World" in result.text
    assert "test document for extraction" in result.text


def test_pptx_extractor_returns_empty_for_missing_file() -> None:
    extractor = PptxExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.pptx")

    assert result.text == ""


def test_pptx_extractor_returns_empty_for_bad_zip(tmp_path: Path) -> None:
    """zipfile.BadZipFile from a truncated PPTX must return '' not propagate."""
    p = tmp_path / "bad.pptx"
    p.write_bytes(b"PK\x03\x04truncated")
    with patch(
        "services.extraction.pptx_extractor.Presentation", side_effect=zipfile.BadZipFile("bad zip")
    ):
        result = PptxExtractor().extract(p)
    assert result.text == ""


def test_pptx_extractor_returns_empty_for_value_error(tmp_path: Path) -> None:
    """ValueError from python-pptx must return '' not propagate."""
    p = tmp_path / "bad.pptx"
    p.write_bytes(b"not a pptx")
    with patch(
        "services.extraction.pptx_extractor.Presentation", side_effect=ValueError("invalid file")
    ):
        result = PptxExtractor().extract(p)
    assert result.text == ""


def test_pptx_extractor_returns_location_segments() -> None:
    """PptxExtractor should emit one LocationSegment per slide with slide number."""
    mock_shape_1 = MagicMock()
    mock_shape_1.text = "Slide 1 Title"
    mock_shape_1.has_text = True
    mock_shape_2 = MagicMock()
    mock_shape_2.text = "Slide 2 body"
    mock_shape_2.has_text = True

    mock_slide_1 = MagicMock()
    mock_slide_1.shapes = [mock_shape_1]
    mock_slide_2 = MagicMock()
    mock_slide_2.shapes = [mock_shape_2]

    mock_prs = MagicMock()
    mock_prs.slides = [mock_slide_1, mock_slide_2]

    with patch("services.extraction.pptx_extractor.Presentation", return_value=mock_prs):
        result = PptxExtractor().extract(Path("/fake.pptx"))

    assert result.text == "Slide 1 Title\nSlide 2 body"
    assert len(result.location_segments) == 2
    assert result.location_segments[0].page_number == 1
    assert result.location_segments[0].start_char == 0
    assert result.location_segments[0].end_char == 13
    assert result.location_segments[1].page_number == 2
    assert result.location_segments[1].start_char == 14
    assert result.location_segments[1].end_char == 26


def test_pptx_extractor_empty_slide_skips_segment() -> None:
    """Slides with no text should not produce a location segment."""
    mock_empty_slide = MagicMock()
    mock_empty_slide.shapes = []
    mock_content_slide = MagicMock()
    mock_shape = MagicMock()
    mock_shape.text = "Content"
    mock_shape.has_text = True
    mock_content_slide.shapes = [mock_shape]

    mock_prs = MagicMock()
    mock_prs.slides = [mock_empty_slide, mock_content_slide]

    with patch("services.extraction.pptx_extractor.Presentation", return_value=mock_prs):
        result = PptxExtractor().extract(Path("/fake.pptx"))

    assert result.text == "Content"
    assert len(result.location_segments) == 1
    assert result.location_segments[0].page_number == 2
