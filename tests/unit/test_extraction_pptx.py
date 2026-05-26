from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

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


def test_pptx_extractor_returns_empty_for_bad_zip(tmp_path: Path) -> None:
    """zipfile.BadZipFile from a truncated PPTX must return '' not propagate."""
    p = tmp_path / "bad.pptx"
    p.write_bytes(b"PK\x03\x04truncated")
    with patch(
        "services.extraction.pptx_extractor.Presentation", side_effect=zipfile.BadZipFile("bad zip")
    ):
        result = PptxExtractor().extract(p)
    assert result == ""


def test_pptx_extractor_returns_empty_for_value_error(tmp_path: Path) -> None:
    """ValueError from python-pptx must return '' not propagate."""
    p = tmp_path / "bad.pptx"
    p.write_bytes(b"not a pptx")
    with patch(
        "services.extraction.pptx_extractor.Presentation", side_effect=ValueError("invalid file")
    ):
        result = PptxExtractor().extract(p)
    assert result == ""
