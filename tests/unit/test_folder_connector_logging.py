from __future__ import annotations

import logging
from pathlib import Path

import pytest

from services.connectors.folder import FolderConnector


def test_folder_connector_logs_file_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_text("content")
    original_read_bytes = Path.read_bytes

    def fake_read_bytes(path: Path) -> bytes:
        if path == unreadable:
            raise OSError("permission denied")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    with caplog.at_level(logging.WARNING, logger="services.connectors.folder"):
        docs = list(FolderConnector(str(tmp_path)).fetch_documents())

    assert docs == []
    assert "skipped unreadable file" in caplog.text
    assert str(unreadable) in caplog.text
    assert str(tmp_path) in caplog.text
