"""Tests for MimeDetector and sniff_office_mime."""

from __future__ import annotations

import types
import zipfile
from pathlib import Path
from unittest.mock import patch

from services.extraction.mime_detector import MimeDetector, sniff_office_mime

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _make_magika_result(mime_type: str, score: float) -> object:
    """Return a minimal fake MagikaResult with .score and .output.mime_type."""

    class _Output:
        pass

    out = _Output()
    out.mime_type = mime_type  # type: ignore[attr-defined]

    class _Result:
        pass

    r = _Result()
    r.score = score  # type: ignore[attr-defined]
    r.output = out  # type: ignore[attr-defined]
    return r


def _make_magika_module(mime_type: str, score: float) -> object:
    """Return a fake magika module whose singleton identify_path returns a fixed result."""
    result = _make_magika_result(mime_type, score)

    class _FakeMagika:
        def identify_path(self, path: Path) -> object:
            return result

    fake_mod = types.ModuleType("magika")
    fake_mod.Magika = _FakeMagika  # type: ignore[attr-defined]
    return fake_mod


# --- existing MimeDetector tests -------------------------------------------


def test_detect_falls_back_to_mimetypes_for_known_extension(tmp_path: Path) -> None:
    p = tmp_path / "document.pdf"
    p.write_bytes(b"%PDF-1.4")
    with patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False):
        mime = MimeDetector().detect(p)
    assert mime == "application/pdf"


def test_detect_returns_octet_stream_for_unknown_extension(tmp_path: Path) -> None:
    p = tmp_path / "unknown_file_no_ext"
    p.write_bytes(b"\x00\x01\x02")
    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", False),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False),
    ):
        mime = MimeDetector().detect(p)
    assert mime == "application/octet-stream"


def test_detect_prefers_magic_over_mimetypes(tmp_path: Path) -> None:
    # A file with a .txt extension but "detected" as PDF by magic.
    p = tmp_path / "actually_a_pdf.txt"
    p.write_bytes(b"%PDF-1.4")

    import types

    fake_magic = types.ModuleType("magic")
    fake_magic.from_file = lambda path, mime: "application/pdf"  # type: ignore[attr-defined]

    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", False),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", True),
        patch("services.extraction.mime_detector._magic", fake_magic, create=True),
    ):
        mime = MimeDetector().detect(p)

    assert mime == "application/pdf"


def test_detect_falls_back_when_magic_returns_octet_stream(tmp_path: Path) -> None:
    p = tmp_path / "document.docx"
    p.write_bytes(b"PK")  # ZIP magic bytes

    import types

    fake_magic = types.ModuleType("magic")
    # Magic returns octet-stream → should fall through to mimetypes.
    fake_magic.from_file = lambda path, mime: "application/octet-stream"  # type: ignore[attr-defined]

    with (
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", True),
        patch("services.extraction.mime_detector._magic", fake_magic, create=True),
    ):
        mime = MimeDetector().detect(p)

    # mimetypes maps .docx to the correct OOXML type
    assert "wordprocessingml" in mime or mime == "application/octet-stream"


def test_detect_prefers_extension_over_generic_magic_for_eml(tmp_path: Path) -> None:
    """libmagic returns text/plain for EML (it's text-based); extension wins."""
    p = tmp_path / "email.eml"
    p.write_bytes(b"From: alice@example.com\r\nSubject: Hi\r\n\r\nBody\r\n")

    import types

    fake_magic = types.ModuleType("magic")
    fake_magic.from_file = lambda path, mime: "text/plain"  # type: ignore[attr-defined]

    with (
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", True),
        patch("services.extraction.mime_detector._magic", fake_magic, create=True),
    ):
        mime = MimeDetector().detect(p)

    assert mime == "message/rfc822"


def test_detect_prefers_extension_over_generic_magic_for_epub(tmp_path: Path) -> None:
    """libmagic returns application/zip for EPUB (it's a ZIP); extension wins."""
    p = tmp_path / "book.epub"
    p.write_bytes(b"PK\x03\x04")

    import types

    fake_magic = types.ModuleType("magic")
    fake_magic.from_file = lambda path, mime: "application/zip"  # type: ignore[attr-defined]

    with (
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", True),
        patch("services.extraction.mime_detector._magic", fake_magic, create=True),
    ):
        mime = MimeDetector().detect(p)

    assert mime == "application/epub+zip"


# --- sniff_office_mime: ZIP-based OOXML detection --------------------------


def _make_ooxml_zip(tmp_path: Path, stem: str, marker: str) -> Path:
    """Create a minimal OOXML ZIP containing a single marker entry."""
    p = tmp_path / stem
    with zipfile.ZipFile(str(p), "w") as zf:
        zf.writestr(marker, "<xml/>")
    return p


def test_sniff_docx_by_content(tmp_path: Path) -> None:
    p = _make_ooxml_zip(tmp_path, "nodot", "word/document.xml")
    assert sniff_office_mime(p) == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_sniff_xlsx_by_content(tmp_path: Path) -> None:
    p = _make_ooxml_zip(tmp_path, "nodot", "xl/workbook.xml")
    assert sniff_office_mime(p) == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_sniff_pptx_by_content(tmp_path: Path) -> None:
    p = _make_ooxml_zip(tmp_path, "nodot", "ppt/presentation.xml")
    assert sniff_office_mime(p) == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


def test_sniff_odf_by_content(tmp_path: Path) -> None:
    """ODF files embed their MIME type in a plain-text 'mimetype' entry."""
    odf_mime = "application/vnd.oasis.opendocument.text"
    p = tmp_path / "nodot"
    with zipfile.ZipFile(str(p), "w") as zf:
        zf.writestr("mimetype", odf_mime)
        zf.writestr("content.xml", "<xml/>")
    assert sniff_office_mime(p) == odf_mime


def test_sniff_returns_none_for_plain_zip(tmp_path: Path) -> None:
    """A ZIP with no Office markers returns None — not a spurious MIME."""
    p = tmp_path / "archive.zip"
    with zipfile.ZipFile(str(p), "w") as zf:
        zf.writestr("README.txt", "hello")
    assert sniff_office_mime(p) is None


def test_sniff_returns_ole_marker_for_ole_file(tmp_path: Path) -> None:
    p = tmp_path / "legacy"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512)
    assert sniff_office_mime(p) == "application/x-ole-storage"


def test_sniff_returns_none_for_binary_blob(tmp_path: Path) -> None:
    p = tmp_path / "random"
    p.write_bytes(b"\x00\x01\x02\x03\x04\x05\x06\x07")
    assert sniff_office_mime(p) is None


def test_sniff_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert sniff_office_mime(tmp_path / "does_not_exist") is None


# --- detect() uses sniff_office_mime when no extension and no python-magic --


def test_detect_sniffs_docx_with_no_extension(tmp_path: Path) -> None:
    """MimeDetector falls back to content sniffing for extensionless DOCX."""
    p = _make_ooxml_zip(tmp_path, "nodot", "word/document.xml")
    with patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False):
        mime = MimeDetector().detect(p)
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_detect_sniffs_xlsx_with_no_extension(tmp_path: Path) -> None:
    p = _make_ooxml_zip(tmp_path, "nodot", "xl/workbook.xml")
    with patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False):
        mime = MimeDetector().detect(p)
    assert mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_detect_sniffs_docx_when_magic_returns_zip_and_no_extension(
    tmp_path: Path,
) -> None:
    """libmagic sees DOCX as application/zip; sniff must refine it when no extension."""
    p = _make_ooxml_zip(tmp_path, "nodot", "word/document.xml")

    import types

    fake_magic = types.ModuleType("magic")
    fake_magic.from_file = lambda path, mime: "application/zip"  # type: ignore[attr-defined]

    with (
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", True),
        patch("services.extraction.mime_detector._magic", fake_magic, create=True),
    ):
        mime = MimeDetector().detect(p)

    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# --- registry sniff-and-retry using real fixture files ---------------------


def test_registry_extracts_docx_stored_as_zip(tmp_path: Path) -> None:
    """Simulate a DB record where mime_type='application/zip' for a real DOCX."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from services.extraction.registry import ExtractorRegistry

    reg = ExtractorRegistry()
    result = reg.extract(FIXTURES / "sample.docx", "application/zip")
    assert result.text.strip(), "should recover text via sniff-and-retry"
    assert "Hello" in result.text or "DOCX" in result.text or "extraction" in result.text


def test_registry_extracts_docx_stored_as_octet_stream(tmp_path: Path) -> None:
    """Simulate a DB record where mime_type='application/octet-stream' for a DOCX."""
    from services.extraction.registry import ExtractorRegistry

    reg = ExtractorRegistry()
    result = reg.extract(FIXTURES / "sample.docx", "application/octet-stream")
    assert result.text.strip(), "should recover text via sniff-and-retry"


def test_registry_extracts_xlsx_stored_as_octet_stream() -> None:
    from services.extraction.registry import ExtractorRegistry

    reg = ExtractorRegistry()
    result = reg.extract(FIXTURES / "sample.xlsx", "application/octet-stream")
    assert result.text.strip(), "should recover xlsx via sniff-and-retry"


def test_registry_extracts_xls_stored_as_octet_stream() -> None:
    """OLE XLS with wrong MIME should be recovered via OLE fallback."""
    from services.extraction.registry import ExtractorRegistry

    reg = ExtractorRegistry()
    result = reg.extract(FIXTURES / "sample.xls", "application/octet-stream")
    assert result.text.strip(), "should recover xls via OLE sniff-and-retry"


# --- Magika integration tests -----------------------------------------------


def test_magika_returns_specific_mime_for_docx_no_extension(tmp_path: Path) -> None:
    """Magika high-confidence result is used for an extensionless DOCX."""
    p = _make_ooxml_zip(tmp_path, "nodot", "word/document.xml")

    class _FakeMagika:
        def identify_path(self, path: Path) -> object:
            return _make_magika_result(_DOCX_MIME, 0.99)

    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", True),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False),
        patch("services.extraction.mime_detector._get_magika", return_value=_FakeMagika()),
    ):
        mime = MimeDetector().detect(p)

    assert mime == _DOCX_MIME


def test_magika_returns_specific_mime_for_xlsx_no_extension(tmp_path: Path) -> None:
    """Magika correctly identifies XLSX without file extension."""
    p = _make_ooxml_zip(tmp_path, "nodot", "xl/workbook.xml")

    class _FakeMagika:
        def identify_path(self, path: Path) -> object:
            return _make_magika_result(_XLSX_MIME, 0.999)

    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", True),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False),
        patch("services.extraction.mime_detector._get_magika", return_value=_FakeMagika()),
    ):
        mime = MimeDetector().detect(p)

    assert mime == _XLSX_MIME


def test_magika_low_confidence_falls_through_to_mimetypes(tmp_path: Path) -> None:
    """A low-confidence Magika result is ignored; mimetypes extension guess wins."""
    p = tmp_path / "report.pdf"
    p.write_bytes(b"%PDF-1.4")

    class _FakeMagika:
        def identify_path(self, path: Path) -> object:
            # Score below threshold — should not be used.
            return _make_magika_result("text/plain", 0.50)

    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", True),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False),
        patch("services.extraction.mime_detector._get_magika", return_value=_FakeMagika()),
    ):
        mime = MimeDetector().detect(p)

    # Mimetypes maps .pdf → application/pdf.
    assert mime == "application/pdf"


def test_magika_generic_result_defers_to_extension(tmp_path: Path) -> None:
    """Magika generic text/plain with high confidence yields to extension for EML."""
    p = tmp_path / "email.eml"
    p.write_bytes(b"From: alice@example.com\r\nSubject: Hi\r\n\r\nBody\r\n")

    class _FakeMagika:
        def identify_path(self, path: Path) -> object:
            # Magika confidently says text/plain (same as libmagic for EML).
            return _make_magika_result("text/plain", 0.90)

    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", True),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False),
        patch("services.extraction.mime_detector._get_magika", return_value=_FakeMagika()),
    ):
        mime = MimeDetector().detect(p)

    # text/plain is generic; .eml extension wins → message/rfc822.
    assert mime == "message/rfc822"


def test_magika_unavailable_falls_through_to_python_magic(tmp_path: Path) -> None:
    """When Magika is not installed the python-magic layer fires as normal."""
    p = tmp_path / "nodot"
    p.write_bytes(b"%PDF-1.4 real content here")

    fake_magic = types.ModuleType("magic")
    fake_magic.from_file = lambda path, mime: "application/pdf"  # type: ignore[attr-defined]

    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", False),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", True),
        patch("services.extraction.mime_detector._magic", fake_magic, create=True),
    ):
        mime = MimeDetector().detect(p)

    assert mime == "application/pdf"


def test_magika_exception_falls_through_gracefully(tmp_path: Path) -> None:
    """An exception inside Magika is caught and the next layer fires."""
    p = tmp_path / "document.pdf"
    p.write_bytes(b"%PDF-1.4")

    class _BrokenMagika:
        def identify_path(self, path: Path) -> object:
            raise RuntimeError("model load failed")

    with (
        patch("services.extraction.mime_detector._MAGIKA_AVAILABLE", True),
        patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False),
        patch("services.extraction.mime_detector._get_magika", return_value=_BrokenMagika()),
    ):
        mime = MimeDetector().detect(p)

    # Falls through to mimetypes → application/pdf from .pdf extension.
    assert mime == "application/pdf"


def test_magika_real_fixtures_detected_correctly() -> None:
    """Smoke-test: Magika correctly identifies real fixture files end-to-end."""
    import pytest

    pytest.importorskip("magika", reason="magika not installed")

    import services.extraction.mime_detector as _mod

    # Reset the singleton so this test gets a fresh Magika instance.
    original = _mod._magika_singleton
    _mod._magika_singleton = None
    try:
        for filename, expected_mime in [
            ("sample.docx", _DOCX_MIME),
            ("sample.xlsx", _XLSX_MIME),
            ("sample.pdf", "application/pdf"),
        ]:
            path = FIXTURES / filename
            if not path.exists():
                continue
            mime = MimeDetector().detect(path)
            assert mime == expected_mime, f"{filename}: got {mime!r}, want {expected_mime!r}"
    finally:
        _mod._magika_singleton = original
