"""Unit tests for services.pipeline.original_store.move_to_originals."""

from __future__ import annotations

from pathlib import Path

from services.pipeline.original_store import move_to_originals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(tmp_path: Path, name: str = "doc.pdf", content: bytes = b"data") -> Path:
    f = tmp_path / name
    f.write_bytes(content)
    return f


# ---------------------------------------------------------------------------
# Skip cases
# ---------------------------------------------------------------------------


def test_returns_none_for_none_path(tmp_path: Path) -> None:
    assert move_to_originals(None, "application/pdf", tmp_path) is None


def test_returns_none_for_audio(tmp_path: Path) -> None:
    src = _make_file(tmp_path, "song.mp3")
    result = move_to_originals(str(src), "audio/mpeg", tmp_path)
    assert result is None
    assert src.exists(), "audio file must not be moved"


def test_returns_none_for_video(tmp_path: Path) -> None:
    src = _make_file(tmp_path, "clip.mp4")
    result = move_to_originals(str(src), "video/mp4", tmp_path)
    assert result is None
    assert src.exists(), "video file must not be moved"


def test_returns_none_for_missing_file(tmp_path: Path) -> None:
    result = move_to_originals(str(tmp_path / "ghost.pdf"), "application/pdf", tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Already inside files_root — no copy
# ---------------------------------------------------------------------------


def test_already_inside_files_root_returns_as_is(tmp_path: Path) -> None:
    files_root = tmp_path / "data"
    files_root.mkdir()
    src = _make_file(files_root, "report.pdf")

    result = move_to_originals(str(src), "application/pdf", files_root)

    assert result == str(src.resolve())
    assert src.exists(), "file inside files_root must not be moved"


# ---------------------------------------------------------------------------
# Outside files_root — moved to originals/
# ---------------------------------------------------------------------------


def test_temp_file_moved_to_originals(tmp_path: Path) -> None:
    files_root = tmp_path / "data"
    files_root.mkdir()
    src = tmp_path / "tmpfile.pdf"
    src.write_bytes(b"pdf content")

    result = move_to_originals(str(src), "application/pdf", files_root)

    assert result is not None
    dest = Path(result)
    assert dest.exists(), "moved file must exist at dest"
    assert dest.is_relative_to(files_root / "originals")
    assert dest.suffix == ".pdf"
    assert dest.read_bytes() == b"pdf content"
    assert not src.exists(), "source temp file must be gone after move"


def test_originals_dir_created_if_missing(tmp_path: Path) -> None:
    files_root = tmp_path / "data"
    files_root.mkdir()
    src = tmp_path / "tmpfile.docx"
    src.write_bytes(b"docx")

    result = move_to_originals(str(src), "application/msword", files_root)

    assert result is not None
    assert (files_root / "originals").is_dir()


def test_extension_preserved(tmp_path: Path) -> None:
    files_root = tmp_path / "data"
    files_root.mkdir()
    src = tmp_path / "slide.pptx"
    src.write_bytes(b"pptx")

    result = move_to_originals(str(src), "application/vnd.ms-powerpoint", files_root)

    assert result is not None
    assert Path(result).suffix == ".pptx"


def test_unique_filenames_for_multiple_files(tmp_path: Path) -> None:
    files_root = tmp_path / "data"
    files_root.mkdir()

    paths = []
    for i in range(3):
        src = tmp_path / f"tmp{i}.pdf"
        src.write_bytes(b"pdf")
        result = move_to_originals(str(src), "application/pdf", files_root)
        assert result is not None
        paths.append(result)

    assert len(set(paths)) == 3, "each file must get a unique storage path"


# ---------------------------------------------------------------------------
# No-extension files
# ---------------------------------------------------------------------------


def test_file_without_extension(tmp_path: Path) -> None:
    files_root = tmp_path / "data"
    files_root.mkdir()
    src = tmp_path / "noext"
    src.write_bytes(b"raw")

    result = move_to_originals(str(src), "application/octet-stream", files_root)

    assert result is not None
    assert Path(result).suffix == ""
