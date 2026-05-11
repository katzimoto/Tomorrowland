"""Unit tests for the SMB source connector."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import services.connectors.smb as smb_module
from services.connectors.smb import SmbConnector

SECRET = "super-secret-password"


class _FakeEntry:
    def __init__(self, name: str, *, is_dir: bool, size: int = 0, mtime: float = 0.0) -> None:
        self.name = name
        self._is_dir = is_dir
        self._stat = SimpleNamespace(st_size=size, st_mtime=mtime)

    def is_dir(self) -> bool:
        return self._is_dir

    def stat(self) -> SimpleNamespace:
        return self._stat


class _FakeSmbClient:
    def __init__(self) -> None:
        self.sessions: list[dict[str, Any]] = []
        self.directories: dict[str, list[_FakeEntry]] = {}
        self.files: dict[str, bytes] = {}
        self.scandir_error: Exception | None = None
        self.open_error: Exception | None = None

    def register_session(self, server: str, **kwargs: Any) -> None:
        self.sessions.append({"server": server, **kwargs})

    def scandir(self, path: str) -> list[_FakeEntry]:
        if self.scandir_error is not None:
            raise self.scandir_error
        return self.directories[path]

    def open_file(self, path: str, mode: str = "rb") -> Any:
        if self.open_error is not None:
            raise self.open_error
        return _FakeFile(self.files[path])


class _FakeFile:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._position = 0

    def __enter__(self) -> _FakeFile:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        chunk = self._content[self._position : self._position + size]
        self._position += len(chunk)
        return chunk


def _config(**overrides: str) -> dict[str, str]:
    config = {
        "server": "fileserver.local",
        "share": "department",
        "base_path": "/legal/contracts",
        "domain": "CORP",
        "username": "svc-tomorrowland",
        "password": SECRET,
    }
    config.update(overrides)
    return config


def _install_fake(monkeypatch: pytest.MonkeyPatch, fake: _FakeSmbClient) -> None:
    monkeypatch.setattr(smb_module, "smbclient", fake)


def test_missing_required_config_fails_validation() -> None:
    with pytest.raises(ValueError, match="server, share, username, password"):
        SmbConnector({}).validate()


def test_password_field_is_sensitive() -> None:
    fields = {field.key: field for field in SmbConnector.fields()}

    assert fields["password"].sensitive is True


def test_valid_config_returns_expected_field_metadata() -> None:
    fields = {field.key: field for field in SmbConnector.fields()}

    assert fields["server"].placeholder == "fileserver.local"
    assert fields["share"].placeholder == "department"
    assert fields["base_path"].required is False
    assert fields["recursive"].required is False


def test_files_yield_stable_external_ids_sha256_temp_path_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSmbClient()
    root = r"\\fileserver.local\department\legal\contracts"
    report = r"\\fileserver.local\department\legal\contracts\report.txt"
    fake.directories[root] = [_FakeEntry("report.txt", is_dir=False, size=11, mtime=42.5)]
    fake.files[report] = b"hello world"
    _install_fake(monkeypatch, fake)

    docs = list(SmbConnector(_config()).fetch_documents())

    assert len(docs) == 1
    doc = docs[0]
    assert doc.external_id == "smb://fileserver.local/department/legal/contracts/report.txt"
    assert doc.title == "report.txt"
    assert doc.mime_type == "text/plain"
    assert doc.sha256 == hashlib.sha256(b"hello world").hexdigest()
    assert doc.path is not None
    assert Path(doc.path).read_bytes() == b"hello world"
    assert doc.metadata == {
        "server": "fileserver.local",
        "share": "department",
        "remote_path": "legal/contracts/report.txt",
        "size": 11,
        "mtime": 42.5,
    }
    assert SECRET not in doc.external_id
    assert SECRET not in doc.title
    assert SECRET not in str(doc.metadata)
    assert fake.sessions == [
        {
            "server": "fileserver.local",
            "username": "svc-tomorrowland",
            "password": SECRET,
            "domain": "CORP",
        }
    ]


def test_directories_ignored_when_recursive_false(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSmbClient()
    root = r"\\fileserver.local\department\legal\contracts"
    fake.directories[root] = [
        _FakeEntry("folder", is_dir=True),
        _FakeEntry("root.txt", is_dir=False, size=4),
    ]
    fake.files[r"\\fileserver.local\department\legal\contracts\root.txt"] = b"root"
    _install_fake(monkeypatch, fake)

    docs = list(SmbConnector(_config(recursive="false")).fetch_documents())

    assert [doc.title for doc in docs] == ["root.txt"]


def test_recursive_listing_enters_directories(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSmbClient()
    root = r"\\fileserver.local\department\legal\contracts"
    subdir = r"\\fileserver.local\department\legal\contracts\folder"
    nested = r"\\fileserver.local\department\legal\contracts\folder\nested.txt"
    fake.directories[root] = [_FakeEntry("folder", is_dir=True)]
    fake.directories[subdir] = [_FakeEntry("nested.txt", is_dir=False, size=6)]
    fake.files[nested] = b"nested"
    _install_fake(monkeypatch, fake)

    docs = list(SmbConnector(_config()).fetch_documents())

    assert [doc.external_id for doc in docs] == [
        "smb://fileserver.local/department/legal/contracts/folder/nested.txt"
    ]


def test_include_exclude_globs_work(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSmbClient()
    root = r"\\fileserver.local\department\legal\contracts"
    fake.directories[root] = [
        _FakeEntry("keep.pdf", is_dir=False, size=4),
        _FakeEntry("skip.pdf", is_dir=False, size=4),
        _FakeEntry("notes.txt", is_dir=False, size=5),
    ]
    fake.files[r"\\fileserver.local\department\legal\contracts\keep.pdf"] = b"keep"
    _install_fake(monkeypatch, fake)

    docs = list(
        SmbConnector(_config(include_globs="**/*.pdf", exclude_globs="skip.pdf")).fetch_documents()
    )

    assert [doc.title for doc in docs] == ["keep.pdf"]


def test_max_file_size_skips_oversized_files(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSmbClient()
    root = r"\\fileserver.local\department\legal\contracts"
    small = r"\\fileserver.local\department\legal\contracts\small.bin"
    fake.directories[root] = [
        _FakeEntry("small.bin", is_dir=False, size=1024),
        _FakeEntry("large.bin", is_dir=False, size=2 * 1024 * 1024),
    ]
    fake.files[small] = b"small"
    _install_fake(monkeypatch, fake)

    docs = list(SmbConnector(_config(max_file_size_mb="1")).fetch_documents())

    assert [doc.title for doc in docs] == ["small.bin"]


def test_mime_fallback_works(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSmbClient()
    root = r"\\fileserver.local\department\legal\contracts"
    unknown = r"\\fileserver.local\department\legal\contracts\document.unknownext"
    fake.directories[root] = [_FakeEntry("document.unknownext", is_dir=False, size=4)]
    fake.files[unknown] = b"data"
    _install_fake(monkeypatch, fake)

    docs = list(SmbConnector(_config()).fetch_documents())

    assert docs[0].mime_type == "application/octet-stream"


@pytest.mark.parametrize("failure", ["auth", "list", "download"])
def test_smb_failures_are_sanitized(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    fake = _FakeSmbClient()
    root = r"\\fileserver.local\department\legal\contracts"
    report = r"\\fileserver.local\department\legal\contracts\report.txt"
    fake.directories[root] = [_FakeEntry("report.txt", is_dir=False, size=11)]
    fake.files[report] = b"hello world"
    if failure == "auth":
        monkeypatch.setattr(
            fake,
            "register_session",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(SECRET)),
        )
    elif failure == "list":
        fake.scandir_error = RuntimeError(SECRET)
    else:
        fake.open_error = RuntimeError(SECRET)
    _install_fake(monkeypatch, fake)

    with pytest.raises(ValueError) as exc_info:
        list(SmbConnector(_config()).fetch_documents())

    message = str(exc_info.value)
    assert "SMB" in message
    assert SECRET not in message
    assert "svc-tomorrowland" not in message
