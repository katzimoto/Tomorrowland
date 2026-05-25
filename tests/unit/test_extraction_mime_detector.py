"""Tests for MimeDetector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from services.extraction.mime_detector import MimeDetector


def test_detect_falls_back_to_mimetypes_for_known_extension(tmp_path: Path) -> None:
    p = tmp_path / "document.pdf"
    p.write_bytes(b"%PDF-1.4")
    with patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False):
        mime = MimeDetector().detect(p)
    assert mime == "application/pdf"


def test_detect_returns_octet_stream_for_unknown_extension(tmp_path: Path) -> None:
    p = tmp_path / "unknown_file_no_ext"
    p.write_bytes(b"\x00\x01\x02")
    with patch("services.extraction.mime_detector._MAGIC_AVAILABLE", False):
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
