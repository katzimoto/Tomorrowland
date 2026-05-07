from __future__ import annotations

from pathlib import Path

from services.extraction.rtf import RtfExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_rtf_extractor_reads_text() -> None:
    extractor = RtfExtractor()
    path = FIXTURES / "sample.rtf"
    rtf = (
        r"{\rtf1\ansi\deff0 {\fonttbl {\f0 Courier;}}"
        r"\f0\fs24 Hello RTF\par test document for extraction}"
    )
    path.write_text(rtf, encoding="utf-8")
    text = extractor.extract(path)
    path.unlink()

    assert "Hello RTF" in text
    assert "test document for extraction" in text


def test_rtf_extractor_returns_empty_for_missing_file() -> None:
    extractor = RtfExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.rtf")

    assert text == ""
