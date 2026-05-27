from __future__ import annotations

from pathlib import Path

from services.extraction.json_extractor import JsonExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_json_extractor_reads_raw_json() -> None:
    extractor = JsonExtractor()
    path = FIXTURES / "sample.json"
    path.write_text('{"key": "Hello JSON", "value": "test document"}', encoding="utf-8")
    result = extractor.extract(path)
    path.unlink()

    assert "Hello JSON" in result.text
    assert "test document" in result.text


def test_json_extractor_returns_empty_for_missing_file() -> None:
    extractor = JsonExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.json")

    assert result.text == ""
