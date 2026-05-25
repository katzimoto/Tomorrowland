"""Tests for ODS and ODP extractors."""

from __future__ import annotations

import zipfile
from pathlib import Path

from services.extraction.opendocument import OdpExtractor, OdsExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"

_ODF_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<office:document-content "
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
    "<text:p>{content}</text:p>"
    "</office:document-content>"
)


def _write_odf(path: Path, content: str) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("content.xml", _ODF_XML.format(content=content))


# ---------------------------------------------------------------------------
# ODS
# ---------------------------------------------------------------------------


def test_ods_extractor_reads_text() -> None:
    path = FIXTURES / "sample.ods"
    _write_odf(path, "Sheet cell value")
    text = OdsExtractor().extract(path)
    path.unlink()
    assert "Sheet cell value" in text


def test_ods_extractor_missing_file_returns_empty() -> None:
    assert OdsExtractor().extract(FIXTURES / "nonexistent.ods") == ""


def test_ods_extractor_invalid_zip_returns_empty() -> None:
    path = FIXTURES / "bad.ods"
    path.write_text("not a zip", encoding="utf-8")
    text = OdsExtractor().extract(path)
    path.unlink()
    assert text == ""


# ---------------------------------------------------------------------------
# ODP
# ---------------------------------------------------------------------------


def test_odp_extractor_reads_text() -> None:
    path = FIXTURES / "sample.odp"
    _write_odf(path, "Slide title text")
    text = OdpExtractor().extract(path)
    path.unlink()
    assert "Slide title text" in text


def test_odp_extractor_missing_file_returns_empty() -> None:
    assert OdpExtractor().extract(FIXTURES / "nonexistent.odp") == ""
