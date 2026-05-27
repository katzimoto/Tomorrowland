"""Tests for the EPUB extractor."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.epub import EpubExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_epub_extractor_returns_empty_when_ebooklib_missing() -> None:
    with patch.dict("sys.modules", {"ebooklib": None, "ebooklib.epub": None}):
        # Re-import so the ImportError path is exercised.
        import importlib

        import services.extraction.epub as epub_mod

        importlib.reload(epub_mod)
        extractor = epub_mod.EpubExtractor()
        assert extractor.extract(FIXTURES / "sample.epub").text == ""


def test_epub_extractor_returns_empty_for_missing_file() -> None:
    extractor = EpubExtractor()
    # ebooklib will raise when the file doesn't exist; extractor must return "".
    assert extractor.extract(FIXTURES / "nonexistent.epub").text == ""


def test_epub_extractor_strips_html_and_joins_spine() -> None:
    """Verify HTML stripping via a fully mocked ebooklib."""
    mock_item = MagicMock()
    mock_item.get_content.return_value = b"<html><body><p>Hello EPUB</p></body></html>"

    mock_book = MagicMock()
    mock_book.get_items_of_type.return_value = [mock_item]

    # Build a fake ebooklib package so the lazy import inside extract() succeeds.
    fake_ebooklib = types.ModuleType("ebooklib")
    fake_ebooklib.ITEM_DOCUMENT = 9  # type: ignore[attr-defined]
    fake_epub_mod = types.ModuleType("ebooklib.epub")
    fake_epub_mod.read_epub = MagicMock(return_value=mock_book)  # type: ignore[attr-defined]
    fake_ebooklib.epub = fake_epub_mod  # type: ignore[attr-defined]

    with patch.dict(sys.modules, {"ebooklib": fake_ebooklib, "ebooklib.epub": fake_epub_mod}):
        extractor = EpubExtractor()
        result = extractor.extract(FIXTURES / "dummy.epub")

    assert "Hello EPUB" in result.text
    assert "<p>" not in result.text
