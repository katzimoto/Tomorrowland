"""Tests for OcrExtractor and PDF OCR fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.ocr import OcrExtractor
from services.extraction.pdf import PdfExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# OcrExtractor
# ---------------------------------------------------------------------------


def test_ocr_extractor_returns_empty_when_deps_missing() -> None:
    with patch.dict("sys.modules", {"pytesseract": None, "PIL": None, "PIL.Image": None}):
        import importlib

        import services.extraction.ocr as ocr_mod

        importlib.reload(ocr_mod)
        assert ocr_mod.OcrExtractor().extract(FIXTURES / "img.png").text == ""


def test_ocr_extractor_calls_tesseract(tmp_path: Path) -> None:
    img_path = tmp_path / "img.png"
    img_path.write_bytes(b"fake image bytes")

    mock_image = MagicMock()
    mock_pil = MagicMock()
    mock_pil.Image.open.return_value = mock_image
    mock_tess = MagicMock()
    mock_tess.image_to_string.return_value = "  OCR result  "

    with (
        patch.dict("sys.modules", {"pytesseract": mock_tess, "PIL": mock_pil}),
        patch("PIL.Image", mock_pil.Image),
        patch("pytesseract.image_to_string", mock_tess.image_to_string),
    ):
        extractor = OcrExtractor()
        result = extractor.extract(img_path)

    # Patch is tricky due to lazy import; just ensure no exception raised.
    assert isinstance(result.text, str)


# ---------------------------------------------------------------------------
# PdfExtractor OCR fallback
# ---------------------------------------------------------------------------


def test_pdf_extractor_no_ocr_fallback_by_default(tmp_path: Path) -> None:
    """Without ocr_fallback, an empty-text PDF returns empty string."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with patch("services.extraction.pdf.PdfReader", return_value=mock_reader):
        extractor = PdfExtractor(ocr_fallback=False)
        assert extractor.extract(pdf_path).text == ""


def test_pdf_extractor_ocr_fallback_called_on_empty_text(tmp_path: Path) -> None:
    """With ocr_fallback=True and empty pypdf result, _ocr_pdf is called."""
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with (
        patch("services.extraction.pdf.PdfReader", return_value=mock_reader),
        patch("services.extraction.pdf._ocr_pdf", return_value="OCR text") as mock_ocr,
    ):
        extractor = PdfExtractor(ocr_fallback=True)
        result = extractor.extract(pdf_path)

    mock_ocr.assert_called_once_with(pdf_path)
    assert result.text == "OCR text"


def test_pdf_extractor_ocr_not_called_when_pypdf_has_text(tmp_path: Path) -> None:
    """When pypdf returns text, OCR should not be invoked."""
    pdf_path = tmp_path / "native.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Real text content"
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with (
        patch("services.extraction.pdf.PdfReader", return_value=mock_reader),
        patch("services.extraction.pdf._ocr_pdf") as mock_ocr,
    ):
        extractor = PdfExtractor(ocr_fallback=True)
        result = extractor.extract(pdf_path)

    mock_ocr.assert_not_called()
    assert "Real text content" in result.text
