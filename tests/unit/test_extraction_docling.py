"""Tests for DoclingPdfExtractor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.base import QualityTier
from services.extraction.docling_extractor import DoclingPdfExtractor
from services.extraction.registry import ExtractorRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_docling_modules(md_text: str) -> dict[str, MagicMock]:
    """Return a sys.modules patch dict that makes docling produce *md_text*."""
    mock_doc = MagicMock()
    mock_doc.export_to_markdown.return_value = md_text

    mock_conv_result = MagicMock()
    mock_conv_result.document = mock_doc

    mock_converter_instance = MagicMock()
    mock_converter_instance.convert.return_value = mock_conv_result

    mock_converter_cls = MagicMock(return_value=mock_converter_instance)

    mock_dc_module = MagicMock()
    mock_dc_module.DocumentConverter = mock_converter_cls

    return {
        "docling": MagicMock(__version__="2.0.0"),
        "docling.document_converter": mock_dc_module,
    }


def _unavailable_docling_modules() -> dict[str, None]:
    """Return a sys.modules patch that makes docling unavailable (ImportError)."""
    return {
        "docling": None,
        "docling.document_converter": None,
    }


# ---------------------------------------------------------------------------
# capabilities()
# ---------------------------------------------------------------------------


def test_capabilities_parser_name() -> None:
    caps = DoclingPdfExtractor().capabilities()
    assert caps.parser_name == "docling_pdf"


def test_capabilities_quality_tier_is_high() -> None:
    caps = DoclingPdfExtractor().capabilities()
    assert caps.quality_tier == QualityTier.HIGH


def test_capabilities_supports_pdf_mime() -> None:
    caps = DoclingPdfExtractor().capabilities()
    assert "application/pdf" in caps.supported_mime_types


def test_capabilities_version_when_docling_missing() -> None:
    with patch.dict("sys.modules", _unavailable_docling_modules()):
        caps = DoclingPdfExtractor().capabilities()
    assert caps.parser_version == "not-installed"


def test_capabilities_version_when_docling_installed() -> None:
    with patch.dict("sys.modules", _mock_docling_modules("")):
        caps = DoclingPdfExtractor().capabilities()
    assert caps.parser_version == "2.0.0"


# ---------------------------------------------------------------------------
# extract() — path guard
# ---------------------------------------------------------------------------


def test_extract_returns_empty_for_nonexistent_file() -> None:
    result = DoclingPdfExtractor().extract(Path("/tmp/does-not-exist-xyz.pdf"))
    assert result.text == ""


# ---------------------------------------------------------------------------
# extract() — docling not installed
# ---------------------------------------------------------------------------


def test_extract_returns_empty_when_docling_not_installed(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch.dict("sys.modules", _unavailable_docling_modules()):
        result = DoclingPdfExtractor().extract(pdf)

    assert result.text == ""


# ---------------------------------------------------------------------------
# extract() — successful conversion
# ---------------------------------------------------------------------------


def test_extract_returns_markdown_text(tmp_path: Path) -> None:
    pdf = tmp_path / "layout.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    expected = "# Heading\n\nParagraph.\n\n| A | B |\n|---|---|\n| 1 | 2 |"

    with patch.dict("sys.modules", _mock_docling_modules(expected)):
        result = DoclingPdfExtractor().extract(pdf)

    assert result.text == expected


def test_extract_calls_converter_with_file_path(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    mods = _mock_docling_modules("# Body")
    mock_instance = mods["docling.document_converter"].DocumentConverter.return_value

    with patch.dict("sys.modules", mods):
        DoclingPdfExtractor().extract(pdf)

    mock_instance.convert.assert_called_once_with(str(pdf))


def test_extract_strips_leading_trailing_whitespace(tmp_path: Path) -> None:
    pdf = tmp_path / "ws.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch.dict("sys.modules", _mock_docling_modules("  \n# Title\n\nBody\n  ")):
        result = DoclingPdfExtractor().extract(pdf)

    assert result.text == "# Title\n\nBody"


# ---------------------------------------------------------------------------
# extract() — empty output from Docling
# ---------------------------------------------------------------------------


def test_extract_returns_empty_when_docling_produces_empty_markdown(tmp_path: Path) -> None:
    pdf = tmp_path / "empty.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch.dict("sys.modules", _mock_docling_modules("")):
        result = DoclingPdfExtractor().extract(pdf)

    assert result.text == ""


def test_extract_returns_empty_when_docling_produces_whitespace_only(tmp_path: Path) -> None:
    pdf = tmp_path / "ws_only.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch.dict("sys.modules", _mock_docling_modules("   \n\n  ")):
        result = DoclingPdfExtractor().extract(pdf)

    assert result.text == ""


# ---------------------------------------------------------------------------
# extract() — conversion exception
# ---------------------------------------------------------------------------


def test_extract_returns_empty_on_conversion_exception(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    mods = _mock_docling_modules("irrelevant")
    converter_mock = mods["docling.document_converter"].DocumentConverter.return_value
    converter_mock.convert.side_effect = RuntimeError("docling internal error")

    with patch.dict("sys.modules", mods):
        result = DoclingPdfExtractor().extract(pdf)

    assert result.text == ""


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_registers_docling_when_enabled() -> None:
    registry = ExtractorRegistry(enable_docling=True)
    assert registry.get_by_name("docling_pdf") is not None


def test_registry_does_not_register_docling_when_disabled() -> None:
    registry = ExtractorRegistry(enable_docling=False)
    assert registry.get_by_name("docling_pdf") is None


def test_registry_docling_reports_high_quality_tier() -> None:
    registry = ExtractorRegistry(enable_docling=True)
    caps = registry.capabilities("docling_pdf")
    assert caps is not None
    assert caps.quality_tier == QualityTier.HIGH


def test_registry_docling_sorts_before_pypdf_in_candidates() -> None:
    """docling_pdf (HIGH tier) must appear before the pypdf PdfExtractor (STANDARD)."""
    registry = ExtractorRegistry(enable_docling=True)
    candidates = registry.candidates("application/pdf")
    assert candidates, "expected at least one PDF candidate"
    first_caps = candidates[0].capabilities()  # type: ignore[attr-defined]
    assert first_caps.parser_name == "docling_pdf"
    assert first_caps.quality_tier == QualityTier.HIGH
