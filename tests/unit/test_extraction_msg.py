from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.msg_extractor import MsgExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_msg_extractor_reads_subject_and_body() -> None:
    extractor = MsgExtractor()

    mock_msg = MagicMock()
    mock_msg.subject = "Hello MSG"
    mock_msg.body = "test document for extraction"
    mock_msg.to = "recipient@example.com"
    mock_msg.sender = "sender@example.com"
    mock_msg.attachments = []

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        text = extractor.extract(FIXTURES / "sample.msg")

    assert "Hello MSG" in text
    assert "test document for extraction" in text
    assert "sender@example.com" in text


def test_msg_extractor_returns_empty_for_missing_file() -> None:
    extractor = MsgExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.msg")

    assert text == ""


def test_msg_extractor_includes_attachment_names() -> None:
    extractor = MsgExtractor()

    mock_att = MagicMock()
    mock_att.longFilename = None
    mock_att.filename = None
    mock_att.shortFilename = None
    mock_att.name = "report.pdf"
    mock_att.data = b"pdf bytes"
    mock_att.data_obj = None
    mock_att.payload = None
    mock_att.content_type = "application/pdf"
    mock_att.mime_type = None

    mock_msg = MagicMock()
    mock_msg.subject = "With attachment"
    mock_msg.body = "see attached"
    mock_msg.to = ""
    mock_msg.sender = ""
    mock_msg.date = None
    mock_msg.attachments = [mock_att]

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        text = extractor.extract(FIXTURES / "sample.msg")

    assert "report.pdf" in text


def test_msg_extract_attachments_returns_bytes() -> None:
    extractor = MsgExtractor()

    mock_att = MagicMock()
    mock_att.longFilename = "report.pdf"
    mock_att.filename = None
    mock_att.shortFilename = None
    mock_att.name = None
    mock_att.data = b"PDF bytes"
    mock_att.data_obj = None
    mock_att.payload = None
    mock_att.content_type = "application/pdf"
    mock_att.mime_type = None

    mock_msg = MagicMock()
    mock_msg.subject = "With attachment"
    mock_msg.body = "see attached"
    mock_msg.to = ""
    mock_msg.sender = ""
    mock_msg.attachments = [mock_att]

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        attachments = extractor.extract_attachments(FIXTURES / "sample.msg")

    assert len(attachments) == 1
    assert attachments[0].filename == "report.pdf"
    assert attachments[0].data == b"PDF bytes"
    assert attachments[0].mime_type == "application/pdf"


def test_msg_extract_attachments_skips_empty_data() -> None:
    extractor = MsgExtractor()

    mock_att = MagicMock()
    mock_att.longFilename = "empty.pdf"
    mock_att.filename = None
    mock_att.shortFilename = None
    mock_att.name = None
    mock_att.data = b""  # empty — should be skipped
    mock_att.data_obj = None
    mock_att.payload = None
    mock_att.content_type = "application/pdf"
    mock_att.mime_type = None

    mock_msg = MagicMock()
    mock_msg.subject = "Empty attachment"
    mock_msg.body = ""
    mock_msg.to = ""
    mock_msg.sender = ""
    mock_msg.attachments = [mock_att]

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        attachments = extractor.extract_attachments(FIXTURES / "sample.msg")

    assert attachments == []


def test_msg_extract_attachments_empty_for_missing_file() -> None:
    extractor = MsgExtractor()
    assert extractor.extract_attachments(FIXTURES / "nonexistent.msg") == []
