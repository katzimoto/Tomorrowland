from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from services.extraction.tar_extractor import TarExtractor
from services.extraction.zip_extractor import ZipExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_zip_extractor_lists_filenames() -> None:
    extractor = ZipExtractor()
    path = FIXTURES / "sample.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("file1.txt", "content1")
        zf.writestr("folder/file2.txt", "content2")
    result = extractor.extract(path)
    path.unlink()

    assert "file1.txt" in result.text
    assert "folder/file2.txt" in result.text


def test_zip_extractor_returns_empty_for_missing_file() -> None:
    extractor = ZipExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.zip")

    assert result.text == ""


def test_zip_extractor_returns_empty_for_corrupted_zip() -> None:
    extractor = ZipExtractor()
    path = FIXTURES / "corrupted.zip"
    path.write_text("this is not a zip", encoding="utf-8")
    result = extractor.extract(path)
    path.unlink()

    assert result.text == ""


def test_tar_extractor_lists_filenames() -> None:
    extractor = TarExtractor()
    path = FIXTURES / "sample.tar"
    with tarfile.open(path, "w") as tf:
        import io

        data = b"content"
        info = tarfile.TarInfo(name="file1.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    result = extractor.extract(path)
    path.unlink()

    assert "file1.txt" in result.text


def test_tar_extractor_returns_empty_for_missing_file() -> None:
    extractor = TarExtractor()
    result = extractor.extract(FIXTURES / "nonexistent.tar")

    assert result.text == ""


def test_zip_extractor_traversal_path_listed_safely() -> None:
    """Path components containing '..' are listed as-is, not resolved."""
    extractor = ZipExtractor()
    path = FIXTURES / "traversal.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0:")
        zf.writestr("safe/file.txt", "content")
    result = extractor.extract(path)
    path.unlink()

    assert "../../etc/passwd" in result.text
    assert "safe/file.txt" in result.text


def test_tar_extractor_traversal_path_listed_safely() -> None:
    """Path components containing '..' are listed as-is, not resolved."""
    import io

    extractor = TarExtractor()
    path = FIXTURES / "traversal.tar"
    with tarfile.open(path, "w") as tf:
        data = b"content"
        info = tarfile.TarInfo(name="../../etc/passwd")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        info2 = tarfile.TarInfo(name="safe/file.txt")
        info2.size = len(data)
        tf.addfile(info2, io.BytesIO(data))
    result = extractor.extract(path)
    path.unlink()

    assert "../../etc/passwd" in result.text
    assert "safe/file.txt" in result.text
