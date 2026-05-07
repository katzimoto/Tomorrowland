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
    text = extractor.extract(path)
    path.unlink()

    assert "file1.txt" in text
    assert "folder/file2.txt" in text


def test_zip_extractor_returns_empty_for_missing_file() -> None:
    extractor = ZipExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.zip")

    assert text == ""


def test_zip_extractor_returns_empty_for_corrupted_zip() -> None:
    extractor = ZipExtractor()
    path = FIXTURES / "corrupted.zip"
    path.write_text("this is not a zip", encoding="utf-8")
    text = extractor.extract(path)
    path.unlink()

    assert text == ""


def test_tar_extractor_lists_filenames() -> None:
    extractor = TarExtractor()
    path = FIXTURES / "sample.tar"
    with tarfile.open(path, "w") as tf:
        import io

        data = b"content"
        info = tarfile.TarInfo(name="file1.txt")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    text = extractor.extract(path)
    path.unlink()

    assert "file1.txt" in text


def test_tar_extractor_returns_empty_for_missing_file() -> None:
    extractor = TarExtractor()
    text = extractor.extract(FIXTURES / "nonexistent.tar")

    assert text == ""
