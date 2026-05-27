from __future__ import annotations

from pathlib import Path

from services.extraction.html import HtmlExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_html_extractor_strips_tags_and_returns_text() -> None:
    extractor = HtmlExtractor()
    path = FIXTURES / "sample.html"
    path.write_text(
        "<html><body><h1>Hello HTML</h1><p>test document for extraction</p></body></html>",
        encoding="utf-8",
    )
    result = extractor.extract(path)
    path.unlink()

    assert "Hello HTML" in result.text
    assert "test document for extraction" in result.text
    assert "<html>" not in result.text


def test_html_extractor_skips_script_and_style() -> None:
    extractor = HtmlExtractor()
    path = FIXTURES / "sample.html"
    path.write_text(
        "<html><script>alert('x')</script><body><p>visible</p></body></html>",
        encoding="utf-8",
    )
    result = extractor.extract(path)
    path.unlink()

    assert "visible" in result.text
    assert "alert" not in result.text


def test_html_extractor_returns_empty_for_missing_file() -> None:
    extractor = HtmlExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.html")

    assert result.text == ""
