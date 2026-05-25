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


# ---------------------------------------------------------------------------
# New MIME types (Phase 2)
# ---------------------------------------------------------------------------


def test_registry_finds_ods_extractor() -> None:
    registry = ExtractorRegistry()
    assert registry.get("application/vnd.oasis.opendocument.spreadsheet") is not None


def test_registry_finds_odp_extractor() -> None:
    registry = ExtractorRegistry()
    assert registry.get("application/vnd.oasis.opendocument.presentation") is not None


def test_registry_finds_epub_extractor() -> None:
    registry = ExtractorRegistry()
    assert registry.get("application/epub+zip") is not None


# ---------------------------------------------------------------------------
# Alias resolution (Phase 1)
# ---------------------------------------------------------------------------


def test_registry_resolves_zip_alias() -> None:
    registry = ExtractorRegistry()
    assert registry.get("application/x-zip") is registry.get("application/zip")


def test_registry_resolves_gzip_alias() -> None:
    registry = ExtractorRegistry()
    assert registry.get("application/x-gzip") is registry.get("application/gzip")


def test_registry_resolves_xhtml_alias() -> None:
    registry = ExtractorRegistry()
    assert registry.get("application/xhtml+xml") is registry.get("text/html")


def test_registry_resolves_yaml_alias() -> None:
    registry = ExtractorRegistry()
    assert registry.get("text/yaml") is registry.get("text/plain")


def test_registry_resolves_markdown_alias() -> None:
    registry = ExtractorRegistry()
    assert registry.get("text/x-markdown") is registry.get("text/plain")


# ---------------------------------------------------------------------------
# octet-stream no longer returns garbage text (Phase 1)
# ---------------------------------------------------------------------------


def test_registry_returns_none_for_octet_stream() -> None:
    """application/octet-stream must not be registered to avoid returning binary garbage."""
    registry = ExtractorRegistry()
    assert registry.get("application/octet-stream") is None


# ---------------------------------------------------------------------------
# Feature-flagged extractors
# ---------------------------------------------------------------------------


def test_registry_legacy_office_not_registered_by_default() -> None:
    registry = ExtractorRegistry()
    assert registry.get("application/msword") is None


def test_registry_ocr_not_registered_by_default() -> None:
    registry = ExtractorRegistry()
    assert registry.get("image/png") is None


def test_registry_ocr_registered_when_enabled() -> None:
    from unittest.mock import patch

    # OcrExtractor is lazy-imported inside _register_ocr(); patch at the source.
    with patch("services.extraction.ocr.OcrExtractor"):
        registry = ExtractorRegistry(enable_ocr=True)
    assert registry.get("image/png") is not None
    assert registry.get("image/jpeg") is not None


def test_registry_legacy_office_registered_when_enabled() -> None:
    from unittest.mock import patch

    # LegacyOfficeExtractor is lazy-imported inside _register_legacy_office().
    with patch("services.extraction.legacy_office.LegacyOfficeExtractor"):
        registry = ExtractorRegistry(enable_legacy_office=True)
    assert registry.get("application/msword") is not None
