from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path

import pytest

from services.connectors.folder import FolderConnector


def test_folder_connector_logs_file_read_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unreadable = tmp_path / "unreadable.txt"
    unreadable.write_text("content")
    original_read_bytes = Path.read_bytes

    def fake_read_bytes(path: Path) -> bytes:
        if path == unreadable:
            raise OSError("permission denied")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)

    logger = logging.getLogger("services.connectors.folder")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    original_level = logger.level
    original_propagate = logger.propagate
    try:
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        logger.propagate = False

        with pytest.raises(OSError, match="permission denied"):
            list(FolderConnector(str(tmp_path)).fetch_documents())
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate

    text = stream.getvalue()
    assert "Folder connector failed to read file" in text
    assert str(unreadable) in text
    assert str(tmp_path) in text
