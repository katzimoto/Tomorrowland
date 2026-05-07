from __future__ import annotations

from pathlib import Path

from services.extraction.json_extractor import JsonExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_json_extractor_reads_raw_json() -> None:
    extractor = JsonExtractor()
    path = FIXTURES / "sample.json"
    path.write_text('{"key": "Hello JSON", "value": "test document"}', encoding="utf-8")
    text = extractor.extract(path)
    path.unlink()

    assert "Hello JSON" in text
    assert "test document" in text


def test_json_extractor_returns_empty_for_missing_file() -> None:
    extractor = JsonExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.json")

    assert text == ""
