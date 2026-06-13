from __future__ import annotations

import io
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from pypdf import PdfWriter

from services.preview.office_pdf import (
    OfficeRenderError,
    _convert_to_pdf,
    render_office_pdf,
)


def _make_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_convert_to_pdf_success(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"docx")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        (out_dir / "doc.pdf").write_bytes(_make_pdf(1))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    with patch("services.preview.office_pdf.subprocess.run", side_effect=_fake_run):
        result = _convert_to_pdf(source, out_dir, timeout=30)
    assert result == out_dir / "doc.pdf"


def test_convert_to_pdf_missing_binary(tmp_path: Path) -> None:
    with (
        patch("services.preview.office_pdf.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(OfficeRenderError) as exc,
    ):
        _convert_to_pdf(tmp_path / "d.docx", tmp_path, timeout=30)
    assert exc.value.category == "renderer_unavailable"


def test_convert_to_pdf_timeout(tmp_path: Path) -> None:
    with (
        patch(
            "services.preview.office_pdf.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="soffice", timeout=30),
        ),
        pytest.raises(OfficeRenderError) as exc,
    ):
        _convert_to_pdf(tmp_path / "d.docx", tmp_path, timeout=30)
    assert exc.value.category == "render_timeout"


def test_convert_to_pdf_nonzero_exit(tmp_path: Path) -> None:
    def _fail(cmd, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(cmd, 1, b"", b"conversion error")

    with (
        patch("services.preview.office_pdf.subprocess.run", side_effect=_fail),
        pytest.raises(OfficeRenderError) as exc,
    ):
        _convert_to_pdf(tmp_path / "d.docx", tmp_path, timeout=30)
    assert exc.value.category == "render"


def test_render_office_pdf_builds_artifact_and_page_count(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"docx")
    pdf_bytes = _make_pdf(3)

    def _fake_convert(src: Path, out_dir: Path, timeout: float) -> Path:
        target = out_dir / "doc.pdf"
        target.write_bytes(pdf_bytes)
        return target

    with patch("services.preview.office_pdf._convert_to_pdf", side_effect=_fake_convert):
        rendered = render_office_pdf(source, timeout=30, max_pages=500)

    assert rendered.page_count == 3
    assert rendered.truncated is False
    assert rendered.artifacts["converted-pdf"][1] == "application/pdf"
    assert rendered.artifacts["converted-pdf"][2] == pdf_bytes


def test_render_office_pdf_truncates_over_page_cap(tmp_path: Path) -> None:
    source = tmp_path / "doc.pptx"
    source.write_bytes(b"pptx")

    def _fake_convert(src: Path, out_dir: Path, timeout: float) -> Path:
        target = out_dir / "doc.pdf"
        target.write_bytes(_make_pdf(5))
        return target

    with patch("services.preview.office_pdf._convert_to_pdf", side_effect=_fake_convert):
        rendered = render_office_pdf(source, timeout=30, max_pages=2)

    assert rendered.page_count == 5
    assert rendered.truncated is True
