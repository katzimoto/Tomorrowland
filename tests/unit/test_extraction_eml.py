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
