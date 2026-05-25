"""Tests for LegacyOfficeExtractor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from services.extraction.legacy_office import LegacyOfficeExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_legacy_office_returns_empty_when_soffice_missing(tmp_path: Path) -> None:
    doc = tmp_path / "doc.doc"
    doc.write_bytes(b"fake")
    with patch(
        "subprocess.run",
        side_effect=FileNotFoundError("soffice not found"),
    ):
        assert LegacyOfficeExtractor().extract(doc) == ""


def test_legacy_office_returns_empty_on_timeout(tmp_path: Path) -> None:
    doc = tmp_path / "doc.doc"
    doc.write_bytes(b"fake")
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="soffice", timeout=30),
    ):
        assert LegacyOfficeExtractor().extract(doc) == ""


def test_legacy_office_returns_empty_on_nonzero_exit(tmp_path: Path) -> None:
    doc = tmp_path / "doc.doc"
    doc.write_bytes(b"fake")

    mock_result = subprocess.CompletedProcess(
        args=["soffice"], returncode=1, stdout=b"", stderr=b"error"
    )
    with patch("subprocess.run", return_value=mock_result):
        assert LegacyOfficeExtractor().extract(doc) == ""


def test_legacy_office_reads_converted_txt(tmp_path: Path) -> None:
    doc = tmp_path / "report.doc"
    doc.write_bytes(b"fake")

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        # Write the expected output file into outdir (cmd[5]).
        outdir = Path(str(cmd[5]))
        (outdir / "report.txt").write_text("Converted text content", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    with patch("subprocess.run", side_effect=fake_run):
        text = LegacyOfficeExtractor().extract(doc)

    assert text == "Converted text content"
