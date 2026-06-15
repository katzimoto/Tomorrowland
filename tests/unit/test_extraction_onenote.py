"""Tests for the OneNote ``.one`` extractor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.onenote import OneNoteExtractor

_ONE_MAGIC = b"\xe4\x52\x5c\x7b\x8c\xd8\xa7\x4d\xae\xb1\x53\x78\xd0\x29\x96\xd3"


def _make_one_file(tmp_path: Path, suffix: str = ".one") -> Path:
    """Create a file with a valid OneNote magic header."""
    path = tmp_path / f"notes{suffix}"
    path.write_bytes(_ONE_MAGIC + b"dummy content")
    return path


def _fake_document(properties: list[dict[str, object]]) -> MagicMock:
    """Return a mocked OneDocment whose get_json() returns *properties*."""
    document = MagicMock()
    document.get_json.return_value = {"properties": properties}
    return document


def test_onenote_extractor_returns_empty_for_missing_file() -> None:
    extractor = OneNoteExtractor()
    result = extractor.extract(Path("/nonexistent/notes.one"))
    assert result.text == ""
    assert result.attachments == []


def test_onenote_extractor_returns_empty_for_non_onenote_file(tmp_path: Path) -> None:
    path = tmp_path / "not-one.txt"
    path.write_text("plain text")
    extractor = OneNoteExtractor()
    result = extractor.extract(path)
    assert result.text == ""


def test_onenote_extractor_returns_empty_when_pyonenote_missing(
    tmp_path: Path,
) -> None:
    path = _make_one_file(tmp_path)
    extractor = OneNoteExtractor()
    with patch.dict("sys.modules", {"pyOneNote": None, "pyOneNote.OneDocument": None}):
        result = extractor.extract(path)
    assert result.text == ""


def test_onenote_extractor_extracts_page_title_and_text(tmp_path: Path) -> None:
    path = _make_one_file(tmp_path)
    properties = [
        {
            "type": "jcidPageNode",
            "identity": "page-1",
            "val": {"CachedTitleString": "Project Ideas"},
        },
        {
            "type": "jcidOutlineElementNode",
            "identity": "oe-1",
            "val": {"RichEditTextUnicode": "Build a search engine."},
        },
    ]

    with patch("pyOneNote.OneDocument.OneDocment", return_value=_fake_document(properties)):
        result = OneNoteExtractor().extract(path)

    assert "# Project Ideas" in result.text
    assert "Build a search engine." in result.text


def test_onenote_extractor_extracts_multiple_pages(tmp_path: Path) -> None:
    path = _make_one_file(tmp_path)
    properties = [
        {
            "type": "jcidPageNode",
            "identity": "page-1",
            "val": {"CachedTitleString": "Page One"},
        },
        {
            "type": "jcidOutlineElementNode",
            "identity": "oe-1",
            "val": {"RichEditTextUnicode": "First page content."},
        },
        {
            "type": "jcidPageNode",
            "identity": "page-2",
            "val": {"CachedTitleStringFromPage": "Page Two"},
        },
        {
            "type": "jcidOutlineElementNode",
            "identity": "oe-2",
            "val": {"RichEditTextUnicode": "Second page content."},
        },
    ]

    with patch("pyOneNote.OneDocument.OneDocment", return_value=_fake_document(properties)):
        result = OneNoteExtractor().extract(path)

    assert "# Page One" in result.text
    assert "First page content." in result.text
    assert "# Page Two" in result.text
    assert "Second page content." in result.text
    assert len(result.location_segments) == 2


def test_onenote_extractor_records_embedded_objects(tmp_path: Path) -> None:
    path = _make_one_file(tmp_path)
    properties = [
        {
            "type": "jcidPageNode",
            "identity": "page-1",
            "val": {"CachedTitleString": "Resources"},
        },
        {
            "type": "jcidEmbeddedFileNode",
            "identity": "emb-1",
            "val": {"EmbeddedFileName": "diagram.pdf"},
        },
        {
            "type": "jcidImageNode",
            "identity": "img-1",
            "val": {"ImageFilename": "screenshot.png"},
        },
    ]

    with patch("pyOneNote.OneDocument.OneDocment", return_value=_fake_document(properties)):
        result = OneNoteExtractor().extract(path)

    assert "## Embedded objects" in result.text
    assert "[embedded-file] diagram.pdf" in result.text
    assert "[image] screenshot.png" in result.text


def test_onenote_extractor_ignores_duplicate_text(tmp_path: Path) -> None:
    path = _make_one_file(tmp_path)
    properties = [
        {
            "type": "jcidOutlineElementNode",
            "identity": "oe-1",
            "val": {
                "CachedTitleString": "Same",
                "RichEditTextUnicode": "Same",
            },
        },
    ]

    with patch("pyOneNote.OneDocument.OneDocment", return_value=_fake_document(properties)):
        result = OneNoteExtractor().extract(path)

    # The duplicate should appear only once.
    assert result.text.count("Same") == 1


def test_onenote_extractor_returns_empty_on_parse_error(tmp_path: Path) -> None:
    path = _make_one_file(tmp_path)

    with patch(
        "pyOneNote.OneDocument.OneDocment",
        side_effect=ValueError("corrupt OneNote file"),
    ):
        result = OneNoteExtractor().extract(path)

    assert result.text == ""


def test_onenote_extractor_handles_non_list_properties(tmp_path: Path) -> None:
    path = _make_one_file(tmp_path)

    document = MagicMock()
    document.get_json.return_value = {"properties": "unexpected"}
    with patch("pyOneNote.OneDocument.OneDocment", return_value=document):
        result = OneNoteExtractor().extract(path)

    assert result.text == ""


def test_onenote_extractor_capabilities() -> None:
    caps = OneNoteExtractor().capabilities()
    assert caps.parser_name == "onenote"
    assert "application/ms-onenote" in caps.supported_mime_types


def test_mime_detector_recognizes_one_extension(tmp_path: Path) -> None:
    from services.extraction.mime_detector import detect_mime_type

    path = tmp_path / "notes.one"
    path.write_bytes(_ONE_MAGIC)
    assert detect_mime_type(path) == "application/ms-onenote"


def test_mime_detector_sniffs_one_without_extension(tmp_path: Path) -> None:
    from services.extraction.mime_detector import detect_mime_type

    path = tmp_path / "notes"
    path.write_bytes(_ONE_MAGIC)
    assert detect_mime_type(path) == "application/ms-onenote"


def test_registry_routes_one_mime_to_onenote_extractor() -> None:
    from services.extraction.registry import ExtractorRegistry

    registry = ExtractorRegistry()
    extractor = registry.get("application/ms-onenote")
    assert isinstance(extractor, OneNoteExtractor)


def test_registry_lists_onenote_capabilities() -> None:
    from services.extraction.registry import ExtractorRegistry

    registry = ExtractorRegistry()
    names = {c.parser_name for c in registry.list()}
    assert "onenote" in names
