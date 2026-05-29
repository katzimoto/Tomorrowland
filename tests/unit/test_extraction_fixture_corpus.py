"""Pre-benchmark fixture corpus tests — issue #527.

Covers extraction shape, citation/chunk_index readiness, and failure-mode
behaviour across the fixture files added in the same issue.
"""

from __future__ import annotations

import email.mime.application
import email.mime.multipart
import email.mime.text
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.base import ExtractionResult
from services.extraction.docx import DocxExtractor
from services.extraction.pdf import PdfExtractor
from services.extraction.pptx_extractor import PptxExtractor
from services.extraction.registry import ExtractorRegistry
from services.extraction.xlsx import XlsxExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# DOCX — heading hierarchy + table
# ---------------------------------------------------------------------------


def test_docx_heading_fixture_contains_heading_text() -> None:
    result = DocxExtractor().extract(FIXTURES / "sample-with-headings.docx")

    assert "Main Heading" in result.text
    assert "Sub Heading" in result.text


def test_docx_heading_fixture_contains_table_values() -> None:
    result = DocxExtractor().extract(FIXTURES / "sample-with-headings.docx")

    assert "Col A" in result.text
    assert "Value 1" in result.text


# ---------------------------------------------------------------------------
# PPTX — slide titles
# ---------------------------------------------------------------------------


def test_pptx_extraction_returns_slide_titles() -> None:
    result = PptxExtractor().extract(FIXTURES / "sample.pptx")

    # sample.pptx contains "Hello PPTX World" as the title text
    assert "Hello PPTX World" in result.text


# ---------------------------------------------------------------------------
# XLSX — multiple sheets
# ---------------------------------------------------------------------------


def test_xlsx_multisheet_returns_values_from_all_sheets() -> None:
    result = XlsxExtractor().extract(FIXTURES / "sample-multisheet.xlsx")

    # Sheet1 values
    assert "Alpha" in result.text
    assert "Beta" in result.text
    # Sheet2 values
    assert "Epsilon" in result.text
    assert "Zeta" in result.text


# ---------------------------------------------------------------------------
# EML — body text + attachment child result
# ---------------------------------------------------------------------------


def _build_multipart_eml(tmp_path: Path) -> Path:
    """Write a multipart EML with text/plain, text/html, and a text attachment."""
    msg = email.mime.multipart.MIMEMultipart("mixed")
    msg["Subject"] = "Fixture Corpus EML"
    msg["From"] = "fixture@example.com"

    alt = email.mime.multipart.MIMEMultipart("alternative")
    alt.attach(email.mime.text.MIMEText("EML plain body text", "plain"))
    alt.attach(email.mime.text.MIMEText("<p>EML html body</p>", "html"))
    msg.attach(alt)

    att = email.mime.application.MIMEApplication(
        b"attachment content text",
        _subtype="octet-stream",
        Name="note.txt",
    )
    att["Content-Disposition"] = 'attachment; filename="note.txt"'
    att.add_header("Content-Type", "text/plain", name="note.txt")
    msg.attach(att)

    path = tmp_path / "sample-multipart.eml"
    path.write_bytes(msg.as_bytes())
    return path


def test_eml_returns_body_text(tmp_path: Path) -> None:
    from services.extraction.eml import EmlExtractor

    path = _build_multipart_eml(tmp_path)
    result = EmlExtractor().extract(path)

    assert "EML plain body text" in result.text
    assert "Fixture Corpus EML" in result.text


def test_eml_attachment_child_is_non_empty(tmp_path: Path) -> None:
    from services.extraction.eml import EmlExtractor

    path = _build_multipart_eml(tmp_path)
    result = EmlExtractor().extract(path)

    assert len(result.attachments) >= 1
    assert result.attachments[0].data != b""


# ---------------------------------------------------------------------------
# MSG — subject + sender
# ---------------------------------------------------------------------------


def test_msg_returns_subject_and_sender() -> None:
    from services.extraction.msg_extractor import MsgExtractor

    mock_msg = MagicMock()
    mock_msg.subject = "MSG Fixture Subject"
    mock_msg.body = "MSG fixture body text."
    mock_msg.to = "receiver@example.com"
    mock_msg.sender = "fixture-sender@example.com"
    mock_msg.attachments = []

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        result = MsgExtractor().extract(FIXTURES / "sample.msg")

    assert "MSG Fixture Subject" in result.text
    assert "fixture-sender@example.com" in result.text


# ---------------------------------------------------------------------------
# Scanned PDF — OCR fallback
# ---------------------------------------------------------------------------


def test_scanned_pdf_ocr_fallback_returns_text(tmp_path: Path) -> None:
    """PdfExtractor with ocr_fallback=True must call OCR when pypdf returns empty."""
    pdf_path = tmp_path / "scanned.pdf"

    mock_reader = MagicMock()
    mock_reader.pages = [MagicMock()]
    mock_page = mock_reader.pages[0]
    mock_page.extract_text.return_value = ""

    with (
        patch("services.extraction.pdf.PdfReader", return_value=mock_reader),
        patch("services.extraction.pdf._ocr_pdf", return_value="OCR extracted text") as mock_ocr,
    ):
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        result = PdfExtractor(ocr_fallback=True).extract(pdf_path)

    mock_ocr.assert_called_once_with(pdf_path)
    assert result.text == "OCR extracted text"


def test_scanned_pdf_no_ocr_without_flag(tmp_path: Path) -> None:
    """Without ocr_fallback, empty text PDF must return '' and not call OCR."""
    pdf_path = tmp_path / "scanned.pdf"

    mock_reader = MagicMock()
    mock_reader.pages = [MagicMock()]
    mock_reader.pages[0].extract_text.return_value = ""

    with (
        patch("services.extraction.pdf.PdfReader", return_value=mock_reader),
        patch("services.extraction.pdf._ocr_pdf") as mock_ocr,
    ):
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        result = PdfExtractor(ocr_fallback=False).extract(pdf_path)

    mock_ocr.assert_not_called()
    assert result.text == ""


# ---------------------------------------------------------------------------
# Corrupt PDF
# ---------------------------------------------------------------------------


def test_corrupt_pdf_returns_empty_no_exception() -> None:
    result = PdfExtractor().extract(FIXTURES / "corrupt.pdf")

    assert result.text == ""
    assert result.attachments == []


# ---------------------------------------------------------------------------
# Wrong-extension file — sniff-and-retry
# ---------------------------------------------------------------------------


def test_wrong_extension_docx_is_actually_pptx_sniff_recovers() -> None:
    """wrong-extension.docx is a PPTX; registry sniff-and-retry must recover the content."""
    registry = ExtractorRegistry()
    result = registry.extract(FIXTURES / "wrong-extension.docx", _DOCX_MIME)

    assert result.text != ""
    assert "Wrong Extension Slide Title" in result.text


# ---------------------------------------------------------------------------
# Failure-mode: encrypted PDF
# ---------------------------------------------------------------------------


def test_encrypted_pdf_returns_empty_no_exception() -> None:
    result = PdfExtractor().extract(FIXTURES / "encrypted.pdf")

    assert result.text == ""
    assert result.attachments == []


# ---------------------------------------------------------------------------
# Failure-mode: unsupported MIME type
# ---------------------------------------------------------------------------


def test_unsupported_mime_type_has_extractor_returns_false() -> None:
    registry = ExtractorRegistry()
    assert registry.has_extractor("application/x-unknown-binary-format") is False


def test_text_subtype_mime_has_extractor_returns_true() -> None:
    """All text/* MIME types must be considered extractable (generic fallback)."""
    registry = ExtractorRegistry()
    assert registry.has_extractor("text/x-custom-format") is True


def test_registry_extract_unsupported_mime_returns_result_for_binary(tmp_path: Path) -> None:
    """Binary content with an unregistered MIME type must not crash."""
    f = tmp_path / "unknown.bin"
    f.write_bytes(b"\x00\x01\x02\x03\xff\xfe")
    registry = ExtractorRegistry()
    result = registry.extract(f, "application/x-unknown-binary-format")

    # Must not raise; returns an ExtractionResult (text may or may not be empty
    # depending on whether charset-normalizer can decode the bytes).
    assert isinstance(result, ExtractionResult)
    assert isinstance(result.text, str)
    assert result.attachments == []
