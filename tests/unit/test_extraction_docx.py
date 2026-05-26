from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

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


def test_docx_extractor_returns_empty_for_bad_zip(tmp_path: Path) -> None:
    """zipfile.BadZipFile from a truncated DOCX must return '' not propagate."""
    p = tmp_path / "bad.docx"
    p.write_bytes(b"PK\x03\x04truncated")
    with patch("services.extraction.docx.Document", side_effect=zipfile.BadZipFile("bad zip")):
        result = DocxExtractor().extract(p)
    assert result == ""


def test_docx_extractor_returns_empty_for_value_error(tmp_path: Path) -> None:
    """ValueError from python-docx must return '' not propagate."""
    p = tmp_path / "bad.docx"
    p.write_bytes(b"not a docx")
    with patch("services.extraction.docx.Document", side_effect=ValueError("invalid file")):
        result = DocxExtractor().extract(p)
    assert result == ""
