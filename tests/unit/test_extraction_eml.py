from __future__ import annotations

from pathlib import Path

from services.extraction.eml import EmlExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


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
    text = extractor.extract(path)
    path.unlink()

    assert "Hello EML" in text
    assert "sender@example.com" in text
    assert "test document for extraction" in text


def test_eml_extractor_returns_empty_for_missing_file() -> None:
    extractor = EmlExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.eml")

    assert text == ""
