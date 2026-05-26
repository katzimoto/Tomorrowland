"""Regression tests for extractor bugs fixed in fix/extractor-bugs.

Each test is named after the bug it prevents regressing.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest

from services.extraction.docx import DocxExtractor
from services.extraction.html import HtmlExtractor
from services.extraction.registry import ExtractorRegistry
from services.extraction.rtf import RtfExtractor
from services.extraction.xlsx import XlsxExtractor
from services.extraction.xml_extractor import XmlExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Bug 1: HTML nested skip-tag depth counter
# ---------------------------------------------------------------------------


def test_html_nested_skip_tags_suppressed(tmp_path: Path) -> None:
    """Text inside nested skip elements must not leak into output.

    <nav><style>css</style>still-nav-text</nav>
    Before the fix `_skip` was reset to False on </style>, so
    'still-nav-text' was captured.  After the fix the depth counter keeps
    _skip_depth > 0 until </nav>.
    """
    p = tmp_path / "nested.html"
    p.write_text(
        "<html><body>"
        "<p>visible</p>"
        "<nav><style>.x{color:red}</style>nav-leak-text</nav>"
        "<p>also visible</p>"
        "</body></html>",
        encoding="utf-8",
    )
    text = HtmlExtractor().extract(p)
    assert "visible" in text
    assert "also visible" in text
    assert "nav-leak-text" not in text
    assert ".x{color:red}" not in text


def test_html_deeply_nested_skip_not_leaked(tmp_path: Path) -> None:
    """Three levels of skip nesting: all suppressed until outermost closes."""
    p = tmp_path / "deep.html"
    p.write_text(
        "<html><body>"
        "<nav><div><script>alert(1)</script>inner-nav</div>outer-nav</nav>"
        "<p>content</p>"
        "</body></html>",
        encoding="utf-8",
    )
    text = HtmlExtractor().extract(p)
    assert "content" in text
    assert "alert" not in text
    assert "inner-nav" not in text
    assert "outer-nav" not in text


# ---------------------------------------------------------------------------
# Bug 2: HTML encoding fallback
# ---------------------------------------------------------------------------


def test_html_extractor_latin1_file_not_empty(tmp_path: Path) -> None:
    """An ISO-8859-1 HTML file must not silently return empty string."""
    p = tmp_path / "latin1.html"
    # Write 'café' as raw latin-1 bytes — NOT valid UTF-8.
    p.write_bytes(
        b"<html><body><p>caf\xe9</p></body></html>"
    )
    text = HtmlExtractor().extract(p)
    assert text != ""
    assert "caf" in text  # at minimum the ASCII part must be present


# ---------------------------------------------------------------------------
# Bug 3: RTF encoding fallback
# ---------------------------------------------------------------------------


def test_rtf_extractor_latin1_file_not_empty(tmp_path: Path) -> None:
    """RTF with Windows-1252 extended bytes must not return empty."""
    p = tmp_path / "win1252.rtf"
    # Simple RTF with a Windows-1252 en-dash (0x96) in the text.
    rtf = (
        rb"{\rtf1\ansi\deff0 {\fonttbl {\f0 Courier;}}"
        rb"\f0\fs24 Hello\x96World}"
    )
    p.write_bytes(rtf)
    text = RtfExtractor().extract(p)
    # Must not be empty — at least the ASCII portions are preserved.
    assert text != ""
    assert "Hello" in text


# ---------------------------------------------------------------------------
# Bug 4 + 5: XML extractor strips tags and handles non-UTF-8 encoding
# ---------------------------------------------------------------------------


def test_xml_extractor_strips_tags(tmp_path: Path) -> None:
    """Extracted text must not contain XML markup."""
    p = tmp_path / "doc.xml"
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<root><section><title>Hello XML</title><body>world</body></section></root>",
        encoding="utf-8",
    )
    text = XmlExtractor().extract(p)
    assert "Hello XML" in text
    assert "world" in text
    # Tags must be absent
    assert "<root>" not in text
    assert "<title>" not in text
    assert "<section>" not in text


def test_xml_extractor_handles_iso8859_encoding(tmp_path: Path) -> None:
    """XML with encoding="iso-8859-1" in the prolog must be extracted."""
    p = tmp_path / "latin.xml"
    content = (
        '<?xml version="1.0" encoding="iso-8859-1"?>'
        "<root><item>caf\xe9</item></root>"
    )
    p.write_bytes(content.encode("iso-8859-1"))
    text = XmlExtractor().extract(p)
    assert text != ""
    assert "caf" in text


def test_xml_extractor_returns_empty_for_malformed(tmp_path: Path) -> None:
    p = tmp_path / "bad.xml"
    p.write_text("<unclosed>", encoding="utf-8")
    assert XmlExtractor().extract(p) == ""


# ---------------------------------------------------------------------------
# Bug 6: DOCX merged table cell deduplication
# ---------------------------------------------------------------------------


def test_docx_merged_cells_not_duplicated(tmp_path: Path) -> None:
    """Merged cells must appear exactly once in extracted text."""
    from docx import Document
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()
    table = doc.add_table(rows=1, cols=3)
    # Populate all three cells with distinct text first.
    table.cell(0, 0).text = "CellA"
    table.cell(0, 1).text = "CellB"
    table.cell(0, 2).text = "CellC"
    # Merge columns 0 and 1.
    merged = table.cell(0, 0).merge(table.cell(0, 1))
    merged.text = "MergedAB"

    p = tmp_path / "merged.docx"
    doc.save(str(p))

    text = DocxExtractor().extract(p)
    # "MergedAB" must appear exactly once.
    assert text.count("MergedAB") == 1
    # "CellC" must still be present.
    assert "CellC" in text


# ---------------------------------------------------------------------------
# Bug 7: MSG extractor file-handle leak (close() called)
# ---------------------------------------------------------------------------


def test_msg_extractor_closes_message_after_extract() -> None:
    """extract_msg.Message.close() must be called after extract()."""
    from services.extraction.msg_extractor import MsgExtractor

    mock_msg = MagicMock()
    mock_msg.subject = "Test"
    mock_msg.body = "body text"
    mock_msg.to = ""
    mock_msg.sender = ""
    mock_msg.date = None
    mock_msg.attachments = []

    with patch(
        "services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg
    ):
        MsgExtractor().extract(FIXTURES / "sample.msg")

    mock_msg.close.assert_called_once()


def test_msg_extractor_closes_message_on_exception() -> None:
    """close() must be called even when body extraction raises mid-way."""
    from services.extraction.msg_extractor import MsgExtractor
    from unittest.mock import PropertyMock

    mock_msg = MagicMock()
    mock_msg.subject = "Test"
    mock_msg.body = "body"
    mock_msg.sender = ""
    mock_msg.to = ""
    mock_msg.date = None
    # Iterating attachments raises — triggers the except path inside extract().
    type(mock_msg).attachments = PropertyMock(side_effect=RuntimeError("disk error"))

    with patch(
        "services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg
    ):
        result = MsgExtractor().extract(FIXTURES / "sample.msg")

    # Should not raise; extractor returns "" on any exception.
    assert result == ""
    mock_msg.close.assert_called_once()


def test_msg_extract_attachments_closes_message() -> None:
    """extract_attachments() must close the Message handle."""
    from services.extraction.msg_extractor import MsgExtractor

    mock_msg = MagicMock()
    mock_msg.attachments = []

    with patch(
        "services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg
    ):
        MsgExtractor().extract_attachments(FIXTURES / "sample.msg")

    mock_msg.close.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 8: XLSX workbook closed on exception
# ---------------------------------------------------------------------------


def test_xlsx_workbook_closed_on_exception(tmp_path: Path) -> None:
    """wb.close() must be called even when iteration raises."""
    from unittest.mock import MagicMock, patch

    mock_wb = MagicMock()
    # Simulate a crash while iterating worksheets.
    mock_wb.worksheets = MagicMock(side_effect=RuntimeError("disk error"))

    with patch("services.extraction.xlsx.load_workbook", return_value=mock_wb):
        p = tmp_path / "boom.xlsx"
        p.write_bytes(b"fake")
        result = XlsxExtractor().extract(p)

    assert result == ""
    mock_wb.close.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 9 + 10: Registry alias/dead-entry cleanup
# ---------------------------------------------------------------------------


def test_registry_x_tar_has_extractor() -> None:
    """application/x-tar must still resolve to TarExtractor after alias cleanup."""
    registry = ExtractorRegistry()
    assert registry.get("application/x-tar") is not None


def test_registry_x_zip_compressed_resolves_via_alias() -> None:
    """application/x-zip-compressed must resolve to the same extractor as application/zip."""
    registry = ExtractorRegistry()
    assert registry.get("application/x-zip-compressed") is registry.get("application/zip")
