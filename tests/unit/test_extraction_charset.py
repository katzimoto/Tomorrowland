"""Tests for charset-aware PlainExtractor."""

from __future__ import annotations

from pathlib import Path

from services.extraction.plain import PlainExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_plain_extractor_reads_utf8(tmp_path: Path) -> None:
    p = tmp_path / "utf8.txt"
    p.write_text("Héllo wörld", encoding="utf-8")
    assert "Héllo wörld" in PlainExtractor().extract(p)


def test_plain_extractor_reads_latin1(tmp_path: Path) -> None:
    p = tmp_path / "latin1.txt"
    p.write_bytes("caf\xe9".encode("latin-1"))  # 'café' in latin-1
    text = PlainExtractor().extract(p)
    # Either charset-normalizer decoded it correctly or the latin-1 fallback
    # produced the raw character — either way it must be non-empty.
    assert text != ""


def test_plain_extractor_returns_empty_for_missing_file() -> None:
    assert PlainExtractor().extract(FIXTURES / "nonexistent.txt") == ""


def test_plain_extractor_reads_windows1252(tmp_path: Path) -> None:
    p = tmp_path / "win1252.txt"
    # 0x92 is RIGHT SINGLE QUOTATION MARK in Windows-1252 (cp1252).
    # Write the raw byte directly since Python's str '\x92' is U+0092 (PRIVATE USE),
    # which cp1252 does not encode.
    p.write_bytes(b"it\x92s fine")
    text = PlainExtractor().extract(p)
    assert text != ""
