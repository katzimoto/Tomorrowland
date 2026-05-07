from __future__ import annotations

from pathlib import Path

from services.extraction.registry import ExtractorRegistry

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_registry_finds_extractor_by_mime_type() -> None:
    registry = ExtractorRegistry()

    assert registry.get("text/plain") is not None
    assert registry.get("application/pdf") is not None
    assert (
        registry.get("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        is not None
    )


def test_registry_returns_none_for_unknown_mime_type() -> None:
    registry = ExtractorRegistry()

    assert registry.get("application/unknown") is None


def test_registry_extracts_text_for_known_mime_type() -> None:
    registry = ExtractorRegistry()
    text = registry.extract(FIXTURES / "sample.txt", "text/plain")

    assert "Hello TXT World" in text


def test_registry_returns_empty_for_unknown_mime_type() -> None:
    registry = ExtractorRegistry()
    text = registry.extract(FIXTURES / "sample.txt", "application/unknown")

    assert text == ""


def test_registry_allows_custom_extractor_registration() -> None:
    class FakeExtractor:
        def extract(self, path: Path) -> str:
            return "fake"

    registry = ExtractorRegistry()
    registry.register("fake/type", FakeExtractor())

    assert registry.extract(FIXTURES / "sample.txt", "fake/type") == "fake"
