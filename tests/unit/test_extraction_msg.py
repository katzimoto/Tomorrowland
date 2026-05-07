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
    mock_att.name = "report.pdf"

    mock_msg = MagicMock()
    mock_msg.subject = "With attachment"
    mock_msg.body = "see attached"
    mock_msg.to = ""
    mock_msg.sender = ""
    mock_msg.attachments = [mock_att]

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        text = extractor.extract(FIXTURES / "sample.msg")

    assert "Attachment: report.pdf" in text
