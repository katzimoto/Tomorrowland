from __future__ import annotations

import email
import email.mime.application
import email.mime.multipart
import email.mime.text
from pathlib import Path

from services.extraction.eml import EmlExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _build_eml_with_attachment(attachment_data: bytes, filename: str, ctype: str) -> bytes:
    """Build a minimal multipart EML with one text body and one attachment."""
    msg = email.mime.multipart.MIMEMultipart()
    msg["Subject"] = "Test with attachment"
    msg["From"] = "sender@example.com"
    msg.attach(email.mime.text.MIMEText("body text", "plain"))
    maintype, subtype = ctype.split("/", 1)
    att = email.mime.application.MIMEApplication(attachment_data, _subtype=subtype, Name=filename)
    att["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(att)
    return msg.as_bytes()


def test_eml_extractor_reads_headers_and_body() -> None:
    extractor = EmlExtractor()
    path = FIXTURES / "sample.eml"
    path.write_text(
        "Subject: Hello EML\r\n"
        "From: sender@example.com\r\n"
        "To: receiver@example.com\r\n"
        "Content-Type: text/plain\r\n\r\n"
        "test document for extraction",
        encoding="utf-8",
    )
    result = extractor.extract(path)
    path.unlink()

    assert "Hello EML" in result.text
    assert "sender@example.com" in result.text
    assert "test document for extraction" in result.text


def test_eml_extractor_returns_empty_for_missing_file() -> None:
    extractor = EmlExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.eml")

    assert result.text == ""


def test_eml_extract_attachments_returns_bytes(tmp_path: Path) -> None:
    eml_bytes = _build_eml_with_attachment(b"PDF content here", "report.pdf", "application/pdf")
    eml_file = tmp_path / "test.eml"
    eml_file.write_bytes(eml_bytes)

    extractor = EmlExtractor()
    result = extractor.extract(eml_file)

    assert len(result.attachments) == 1
    assert result.attachments[0].filename == "report.pdf"
    assert result.attachments[0].data == b"PDF content here"
    assert result.attachments[0].mime_type == "application/pdf"


def test_eml_extract_attachments_empty_for_no_attachments(tmp_path: Path) -> None:
    eml_file = tmp_path / "plain.eml"
    eml_file.write_text(
        "Subject: No attachments\r\nContent-Type: text/plain\r\n\r\nbody",
        encoding="utf-8",
    )
    extractor = EmlExtractor()
    assert extractor.extract(eml_file).attachments == []


def test_eml_extract_attachments_empty_for_missing_file(tmp_path: Path) -> None:
    extractor = EmlExtractor()
    assert extractor.extract(tmp_path / "nonexistent.eml").attachments == []


def test_eml_multipart_alternative_body_not_duplicated(tmp_path: Path) -> None:
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = "Alt"
    msg.attach(email.mime.text.MIMEText("Hello world body", "plain"))
    msg.attach(email.mime.text.MIMEText("<p>Hello world body</p>", "html"))
    eml_file = tmp_path / "alt.eml"
    eml_file.write_bytes(msg.as_bytes())

    result = EmlExtractor().extract(eml_file)
    # Plain is preferred; the shared body appears once, not duplicated.
    assert result.text.count("Hello world body") == 1


def test_eml_html_only_uses_html_with_block_spacing(tmp_path: Path) -> None:
    msg = email.mime.text.MIMEText("<p>First line</p><p>Second line</p>", "html")
    msg["Subject"] = "HTML only"
    eml_file = tmp_path / "html.eml"
    eml_file.write_bytes(msg.as_bytes())

    result = EmlExtractor().extract(eml_file)
    assert "First line" in result.text
    assert "Second line" in result.text
    # Block boundaries add whitespace so paragraphs don't run together.
    assert "First lineSecond line" not in result.text
