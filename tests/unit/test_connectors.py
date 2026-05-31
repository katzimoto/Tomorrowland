"""Unit tests for the connectors package."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import RowMapping

from services.connectors.base import ConnectorDocument
from services.connectors.factory import build_connector, connector_types
from services.connectors.folder import FolderConnector
from services.connectors.nifi import NiFiConnector


def _make_row(**kwargs: object) -> RowMapping:
    mock = MagicMock(spec=RowMapping)
    mock.__getitem__ = lambda self, key: kwargs[key]
    mock.get = lambda key, default=None: kwargs.get(key, default)
    return mock


# ── FolderConnector ────────────────────────────────────────────────────────────


def test_folder_connector_yields_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("world")

    docs = list(FolderConnector(str(tmp_path)).fetch_documents())

    assert len(docs) == 2
    assert all(d.external_id.startswith("file:") for d in docs)
    assert all(d.path is not None for d in docs)
    assert all(d.text_content is None for d in docs)
    assert all(d.sha256 is not None and len(d.sha256) == 64 for d in docs)


def test_folder_connector_skips_directories(tmp_path: Path) -> None:
    (tmp_path / "dir").mkdir()
    (tmp_path / "file.txt").write_text("content")

    docs = list(FolderConnector(str(tmp_path)).fetch_documents())

    assert len(docs) == 1


def test_folder_connector_title_is_filename(tmp_path: Path) -> None:
    (tmp_path / "report.pdf").write_bytes(b"%PDF")

    docs = list(FolderConnector(str(tmp_path)).fetch_documents())

    assert docs[0].title == "report.pdf"


def test_folder_connector_validate_ok(tmp_path: Path) -> None:
    FolderConnector(str(tmp_path)).validate()  # must not raise


def test_folder_connector_validate_empty_path() -> None:
    with pytest.raises(ValueError, match="no path"):
        FolderConnector("").validate()


def test_folder_connector_validate_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        FolderConnector(str(tmp_path / "nonexistent")).validate()


def test_folder_connector_fields_returns_path_field() -> None:
    fields = FolderConnector.fields()
    assert len(fields) == 1
    assert fields[0].key == "path"
    assert not fields[0].sensitive


def test_folder_connector_skips_unreadable_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One unreadable file must not abort the sync; readable files still yield."""
    (tmp_path / "readable.txt").write_text("hello")
    (tmp_path / "unreadable.txt").write_text("secret")

    original_read_bytes = Path.read_bytes

    def _patched_read_bytes(self: Path) -> bytes:
        if self.name == "unreadable.txt":
            raise PermissionError("Permission denied")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched_read_bytes)

    docs = list(FolderConnector(str(tmp_path)).fetch_documents())

    assert len(docs) == 1
    assert docs[0].title == "readable.txt"


def test_folder_connector_skips_unreadable_file_logs_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unreadable file should produce a safe warning log."""
    (tmp_path / "readable.txt").write_text("hello")
    (tmp_path / "unreadable.txt").write_text("secret")

    original_read_bytes = Path.read_bytes

    def _patched_read_bytes(self: Path) -> bytes:
        if self.name == "unreadable.txt":
            raise PermissionError("Permission denied")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched_read_bytes)

    with caplog.at_level("WARNING", logger="services.connectors.folder"):
        list(FolderConnector(str(tmp_path)).fetch_documents())

    assert any("skipped unreadable file" in r.message for r in caplog.records)
    assert any("permission_denied" in r.message for r in caplog.records)
    # No file contents leaked
    assert "secret" not in caplog.text


def test_folder_connector_skips_unreadable_file_generic_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generic OSError (not PermissionError) should also be skipped."""
    (tmp_path / "readable.txt").write_text("hello")
    (tmp_path / "broken.txt").write_text("content")

    original_read_bytes = Path.read_bytes

    def _patched_read_bytes(self: Path) -> bytes:
        if self.name == "broken.txt":
            raise OSError("Device I/O error")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", _patched_read_bytes)

    docs = list(FolderConnector(str(tmp_path)).fetch_documents())

    assert len(docs) == 1
    assert docs[0].title == "readable.txt"


# ── NiFiConnector ──────────────────────────────────────────────────────────────


def test_nifi_connector_fields_has_sensitive_token() -> None:
    fields = NiFiConnector.fields()
    keys = {f.key for f in fields}
    assert "api_token" in keys
    token_field = next(f for f in fields if f.key == "api_token")
    assert token_field.sensitive is True


def test_nifi_connector_validate_accepts_event_driven_defaults() -> None:
    NiFiConnector({}).validate()  # optional event-driven settings only


def test_nifi_connector_fetch_documents_is_event_driven_empty_iterator() -> None:
    assert list(NiFiConnector({}).fetch_documents()) == []


# ── Factory ────────────────────────────────────────────────────────────────────


def test_factory_returns_folder_connector() -> None:
    row = _make_row(type="folder", config=None, path="/data/docs")
    assert isinstance(build_connector(row), FolderConnector)


def test_factory_returns_nifi_connector() -> None:
    row = _make_row(
        type="nifi",
        config={"base_url": "http://nifi:8080", "flow_id": "x", "api_token": "t"},
    )
    assert isinstance(build_connector(row), NiFiConnector)


def test_factory_raises_for_unknown_type() -> None:
    row = _make_row(type="sharepoint", config=None)
    with pytest.raises(ValueError, match="Unknown source type"):
        build_connector(row)


def test_factory_raises_when_folder_has_no_path() -> None:
    row = _make_row(type="folder", config=None, path=None)
    with pytest.raises(ValueError, match="no path"):
        build_connector(row)


def test_factory_parses_json_string_config() -> None:
    """SQLite returns JSON columns as strings."""
    row = _make_row(
        type="nifi",
        config=json.dumps({"base_url": "http://nifi", "flow_id": "x", "api_token": "t"}),
    )
    connector = build_connector(row)
    assert isinstance(connector, NiFiConnector)


def test_factory_accepts_empty_json_string_for_nifi() -> None:
    row = _make_row(type="nifi", config="")
    connector = build_connector(row)
    assert isinstance(connector, NiFiConnector)


# ── connector_types metadata ───────────────────────────────────────────────────


def test_connector_types_includes_folder_and_nifi() -> None:
    types = connector_types()
    type_names = {t["type"] for t in types}
    assert "folder" in type_names
    assert "nifi" in type_names


def test_connector_types_include_field_dicts() -> None:
    types = connector_types()
    folder = next(t for t in types if t["type"] == "folder")
    assert isinstance(folder["fields"], list)
    assert len(folder["fields"]) > 0
    field = folder["fields"][0]
    assert {"key", "label", "required", "sensitive", "placeholder"} <= field.keys()


def test_connector_types_nifi_has_sensitive_token_in_metadata() -> None:
    types = connector_types()
    nifi = next(t for t in types if t["type"] == "nifi")
    token = next(f for f in nifi["fields"] if f["key"] == "api_token")
    assert token["sensitive"] is True


# ── Protocol structural check ─────────────────────────────────────────────────


def test_connector_document_is_immutable() -> None:
    doc = ConnectorDocument(
        external_id="x",
        title="t",
        mime_type="text/plain",
        sha256=None,
        source_language=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        doc.title = "changed"  # type: ignore[misc]


# ── Atlassian connectors ──────────────────────────────────────────────────────


def test_confluence_connector_fields_has_sensitive_token() -> None:
    from services.connectors.atlassian import ConfluenceConnector

    fields = ConfluenceConnector.fields()
    keys = {f.key for f in fields}
    assert {"base_url", "api_token", "space_key", "updated_since"} <= keys
    assert next(f for f in fields if f.key == "api_token").sensitive is True


def test_jira_connector_fields_has_sensitive_token() -> None:
    from services.connectors.atlassian import JiraConnector

    fields = JiraConnector.fields()
    keys = {f.key for f in fields}
    assert {"base_url", "api_token", "project_key", "jql", "updated_since"} <= keys
    assert next(f for f in fields if f.key == "api_token").sensitive is True


def test_atlassian_connectors_reject_cloud_urls() -> None:
    from services.connectors.atlassian import ConfluenceConnector, JiraConnector

    with pytest.raises(ValueError, match="Cloud"):
        ConfluenceConnector({"base_url": "https://example.atlassian.net", "api_token": "t"})
    with pytest.raises(ValueError, match="Cloud"):
        JiraConnector({"base_url": "https://example.atlassian.net", "api_token": "t"})


def test_factory_returns_confluence_and_jira_connectors() -> None:
    from services.connectors.atlassian import ConfluenceConnector, JiraConnector

    confluence = _make_row(
        type="confluence",
        config={"base_url": "https://wiki.local", "api_token": "t"},
    )
    jira = _make_row(
        type="jira",
        config={"base_url": "https://jira.local", "api_token": "t"},
    )

    assert isinstance(build_connector(confluence), ConfluenceConnector)
    assert isinstance(build_connector(jira), JiraConnector)


def test_connector_types_includes_atlassian_connectors() -> None:
    types = connector_types()
    type_names = {t["type"] for t in types}
    assert "confluence" in type_names
    assert "jira" in type_names


def _make_fake_response(data: bytes) -> object:
    """Return a file-like object that supports chunked reads for streaming."""

    class _FakeStream:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self._pos = 0

        def __enter__(self) -> _FakeStream:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            if size < 0:
                chunk = self._data[self._pos :]
                self._pos = len(self._data)
                return chunk
            chunk = self._data[self._pos : self._pos + size]
            self._pos += len(chunk)
            return chunk

    return _FakeStream(data)


def test_confluence_connector_fetches_pages_and_attachments() -> None:
    from services.connectors.atlassian import ConfluenceConnector, _DownloadedAttachment

    class StubConfluenceConnector(ConfluenceConnector):
        def _check_confluence_reachability(self) -> None:
            return None  # no-op for tests

        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            if path == "/rest/api/content/search":
                return {
                    "results": [
                        {
                            "id": "123",
                            "title": "Roadmap",
                            "body": {"storage": {"value": "<p>Hello <strong>world</strong></p>"}},
                        }
                    ]
                }
            return {
                "results": [
                    {
                        "id": "att-1",
                        "title": "plan.txt",
                        "metadata": {"mediaType": "text/plain"},
                        "_links": {"download": "/download/att-1"},
                    }
                ]
            }

        def _download_attachment(
            self,
            download_url: str,
            filename: str,
            *,
            storage_root: Path | None = None,
            max_bytes: int | None = None,
        ) -> _DownloadedAttachment:
            assert download_url == "/download/att-1"
            assert filename == "plan.txt"
            return _DownloadedAttachment(path="/tmp/plan.txt", sha256="b" * 64)

    docs = list(
        StubConfluenceConnector(
            {"base_url": "https://wiki.local", "api_token": "t", "space_key": "ENG"}
        ).fetch_documents()
    )

    assert [doc.external_id for doc in docs] == ["confluence:123", "confluence:123:att:att-1"]
    assert docs[0].mime_type == "text/html"
    assert docs[0].text_content == "Hello\nworld"
    assert docs[1].path == "/tmp/plan.txt"
    assert docs[1].mime_type == "text/plain"


def test_jira_connector_fetches_issues_and_attachments() -> None:
    from services.connectors.atlassian import JiraConnector, _DownloadedAttachment

    class StubJiraConnector(JiraConnector):
        def _check_jira_reachability(self) -> None:
            return None  # no-op for tests

        def _request_json(self, path: str, **kwargs: object) -> dict[str, object]:
            assert path == "/rest/api/2/search"
            body = kwargs["body"]
            assert isinstance(body, dict)
            assert "project = ENG" in str(body["jql"])
            return {
                "total": 1,
                "issues": [
                    {
                        "key": "ENG-7",
                        "fields": {
                            "summary": "Fix sync",
                            "description": "Details",
                            "comment": {"comments": [{"body": "Looks good"}]},
                            "attachment": [
                                {
                                    "id": "10001",
                                    "filename": "error.log",
                                    "mimeType": "text/plain",
                                    "content": "https://jira.local/secure/attachment/10001/error.log",
                                }
                            ],
                        },
                    }
                ],
            }

        def _download_attachment(
            self,
            download_url: str,
            filename: str,
            *,
            storage_root: Path | None = None,
            max_bytes: int | None = None,
        ) -> _DownloadedAttachment:
            assert download_url.endswith("/error.log")
            assert filename == "error.log"
            return _DownloadedAttachment(path="/tmp/error.log", sha256="c" * 64)

    docs = list(
        StubJiraConnector(
            {"base_url": "https://jira.local", "api_token": "t", "project_key": "ENG"}
        ).fetch_documents()
    )

    assert [doc.external_id for doc in docs] == ["jira:ENG-7", "jira:ENG-7:att:10001"]
    assert "Summary: Fix sync" in docs[0].text_content
    assert "Details" in docs[0].text_content
    assert "Looks good" in docs[0].text_content
    assert docs[1].path == "/tmp/error.log"
    assert docs[1].mime_type == "text/plain"


def test_atlassian_request_json_uses_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as json_module
    from typing import Any

    import services.connectors.atlassian as atlassian
    from services.connectors.atlassian import JiraConnector

    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: int) -> object:
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return _make_fake_response(json_module.dumps({"ok": True}).encode())

    monkeypatch.setattr(atlassian, "urlopen", fake_urlopen)
    connector = JiraConnector(
        {"base_url": "https://jira.local/root", "username": "alice", "api_token": "secret"}
    )

    payload = connector._request_json("/rest/api/2/myself", query={"expand": "groups"})

    assert payload == {"ok": True}
    assert captured["url"] == "https://jira.local/root/rest/api/2/myself?expand=groups"
    assert captured["auth"] == "Basic YWxpY2U6c2VjcmV0"
    assert captured["timeout"] == 30


def test_atlassian_download_attachment_writes_temp_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Any

    import services.connectors.atlassian as atlassian
    from services.connectors.atlassian import ConfluenceConnector

    captured: dict[str, str] = {}

    def fake_urlopen(request: Any, timeout: int) -> object:
        assert timeout == 30
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        return _make_fake_response(b"attachment-bytes")

    monkeypatch.setattr(atlassian, "urlopen", fake_urlopen)
    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "pat"})

    downloaded = connector._download_attachment("/download/guide.pdf", "guide.pdf")

    assert captured == {
        "url": "https://wiki.local/download/guide.pdf",
        "auth": "Bearer pat",
    }
    assert downloaded.sha256 == "0e22a93c611048eae817350dbce895ca674555e54a921a7f90d36f3e14cd005c"
    assert Path(downloaded.path).read_bytes() == b"attachment-bytes"
    Path(downloaded.path).unlink()


def test_atlassian_validate_rejects_missing_and_invalid_config() -> None:
    from services.connectors.atlassian import ConfluenceConnector, JiraConnector

    with pytest.raises(ValueError, match="requires base_url"):
        ConfluenceConnector({"api_token": "t"}).validate()
    with pytest.raises(ValueError, match="http"):
        JiraConnector({"base_url": "jira.local", "api_token": "t"}).validate()
    with pytest.raises(ValueError, match="api_token"):
        JiraConnector({"base_url": "https://jira.local"}).validate()


def test_jira_connector_handles_adf_description_and_configured_jql() -> None:
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {"base_url": "https://jira.local", "api_token": "t", "jql": "project = OPS"}
    )

    jql = connector._jql()
    assert "project = OPS" in jql
    assert "ORDER BY updated ASC" in jql
    text = connector._issue_text(
        summary="ADF issue",
        fields={
            "description": {
                "content": [
                    {"content": [{"text": "Nested text"}]},
                    {"text": "Second block"},
                ]
            }
        },
    )
    assert "Summary: ADF issue" in text
    assert "Description:" in text
    assert "Nested text" in text
    assert "Second block" in text


def test_confluence_connector_paginates_pages() -> None:
    from services.connectors.atlassian import ConfluenceConnector

    class StubConfluenceConnector(ConfluenceConnector):
        def __init__(self) -> None:
            super().__init__({"base_url": "https://wiki.local", "api_token": "t"})
            self.starts: list[int] = []

        def _check_confluence_reachability(self) -> None:
            return None  # no-op for tests

        def _request_json(self, path: str, **kwargs: object) -> dict[str, object]:
            assert path == "/rest/api/content/search"
            query = kwargs["query"]
            assert isinstance(query, dict)
            start = int(query["start"])
            self.starts.append(start)
            if start == 0:
                return {"results": [{"id": str(i), "title": f"Page {i}"} for i in range(50)]}
            return {"results": [{"id": "50", "title": "Page 50"}]}

        def _fetch_attachments(
            self,
            *,
            page_id: str,
            page_title: str,
            storage_root: Path | None = None,
            max_bytes: int | None = None,
        ) -> Iterator[ConnectorDocument]:
            assert page_id
            assert page_title
            return iter(())

    connector = StubConfluenceConnector()

    docs = list(connector.fetch_documents())

    assert len(docs) == 51
    assert connector.starts == [0, 50]


# ── storage_root direct-write tests ──────────────────────────────────────────


def test_atlassian_download_attachment_writes_to_storage_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When storage_root is provided, attachment bytes are written there directly."""
    from typing import Any

    import services.connectors.atlassian as atlassian
    from services.connectors.atlassian import ConfluenceConnector

    def fake_urlopen(request: Any, timeout: int) -> object:
        return _make_fake_response(b"file-content")

    monkeypatch.setattr(atlassian, "urlopen", fake_urlopen)
    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "pat"})

    storage = tmp_path / "originals"
    downloaded = connector._download_attachment(
        "/download/report.pdf", "report.pdf", storage_root=storage
    )

    # File must land inside storage_root (dir is created on demand)
    assert Path(downloaded.path).parent == storage
    assert Path(downloaded.path).read_bytes() == b"file-content"
    assert downloaded.sha256 == "2239ce4df9ee8db012834642ec801b55ba2c92b28bdd11f4d73d9c55d39f3b0a"


def test_confluence_fetch_documents_passes_storage_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """fetch_documents(storage_root=...) must forward the root to _fetch_attachments."""
    from services.connectors.atlassian import ConfluenceConnector

    received_roots: list[Path | None] = []

    class StubConnector(ConfluenceConnector):
        def _check_confluence_reachability(self) -> None:
            return None  # no-op for tests

        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            if "search" in path:
                return {
                    "results": [
                        {
                            "id": "1",
                            "title": "A Page",
                            "body": {"storage": {"value": "<p>text</p>"}},
                        }
                    ]
                }
            return {"results": []}

        def _fetch_attachments(
            self,
            *,
            page_id: str,
            page_title: str,
            storage_root: Path | None = None,
            max_bytes: int | None = None,
        ) -> Iterator[ConnectorDocument]:
            received_roots.append(storage_root)
            return iter(())

    storage = tmp_path / "originals"
    list(
        StubConnector({"base_url": "https://wiki.local", "api_token": "t"}).fetch_documents(
            storage_root=storage
        )
    )

    assert received_roots == [storage]


def test_jira_fetch_documents_passes_storage_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """fetch_documents(storage_root=...) must forward the root to _fetch_attachments."""
    from services.connectors.atlassian import JiraConnector

    received_roots: list[Path | None] = []

    class StubConnector(JiraConnector):
        def _check_jira_reachability(self) -> None:
            return None  # no-op for tests

        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            return {
                "total": 1,
                "issues": [
                    {
                        "key": "X-1",
                        "fields": {
                            "summary": "Test issue",
                            "description": None,
                            "comment": {},
                            "attachment": [],
                        },
                    }
                ],
            }

        def _fetch_attachments(
            self,
            *,
            issue_key: str,
            fields: dict,
            storage_root: Path | None = None,
            max_bytes: int | None = None,
        ) -> Iterator[ConnectorDocument]:
            received_roots.append(storage_root)
            return iter(())

    storage = tmp_path / "originals"
    list(
        StubConnector({"base_url": "https://jira.local", "api_token": "t"}).fetch_documents(
            storage_root=storage
        )
    )

    assert received_roots == [storage]


# ── Confluence auth_mode tests ────────────────────────────────────────────────


def test_confluence_auth_mode_defaults_to_service_account() -> None:
    """auth_mode defaults to service_account when omitted."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    auth_mode = connector._config_str("auth_mode", "service_account")
    assert auth_mode == "service_account"
    # validate() should pass the auth_mode check (only fails at API reachability)
    # We override _check_confluence_reachability to test just the auth_mode logic


def test_confluence_validate_rejects_unsupported_auth_modes() -> None:
    """Unsupported auth modes are rejected with a clear error."""
    from services.connectors.atlassian import ConfluenceConnector

    with pytest.raises(ValueError, match="auth_mode"):
        connector = ConfluenceConnector(
            {"base_url": "https://wiki.local", "api_token": "t", "auth_mode": "user_delegated"}
        )
        # Override the API check to only test auth_mode validation
        connector._check_confluence_reachability = lambda: None
        connector.validate()


def test_confluence_validate_rejects_unsupported_auth_mode_via_validate() -> None:
    """Validate raises ValueError for unsupported auth modes."""
    from services.connectors.atlassian import ConfluenceConnector

    class NoopConnector(ConfluenceConnector):
        def _check_confluence_reachability(self) -> None:
            return None

    with pytest.raises(ValueError, match="auth_mode"):
        NoopConnector(
            {"base_url": "https://wiki.local", "api_token": "t", "auth_mode": "oauth"}
        ).validate()

    with pytest.raises(ValueError, match="auth_mode"):
        NoopConnector(
            {"base_url": "https://wiki.local", "api_token": "t", "auth_mode": ""}
        ).validate()


# ── Confluence space_keys tests ────────────────────────────────────────────────


def test_confluence_space_keys_omitted_allows_all() -> None:
    """space_keys omitted means no space CQL filter is applied."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    keys = connector._resolve_space_keys()
    assert keys == []
    # CQL should not contain space= when building query
    cql_parts = ["type=page"]
    for key in keys:
        cql_parts.append(f"space={key}")
    assert "space=" not in " AND ".join(cql_parts)


def test_confluence_space_keys_empty_list_allows_all() -> None:
    """space_keys: [] means no space CQL filter."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_keys": []}
    )
    keys = connector._resolve_space_keys()
    assert keys == []


def test_confluence_space_keys_filters_eng() -> None:
    """space_keys: ['ENG'] filters only ENG."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_keys": ["ENG"]}
    )
    keys = connector._resolve_space_keys()
    assert keys == ["ENG"]


def test_confluence_legacy_space_key_maps_to_space_keys() -> None:
    """Legacy space_key maps to space_keys single-element list."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_key": "ENG"}
    )
    keys = connector._resolve_space_keys()
    assert keys == ["ENG"]


def test_confluence_space_keys_takes_precedence_over_legacy() -> None:
    """space_keys takes precedence over legacy space_key when both are set."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "space_key": "OPS",
            "space_keys": ["ENG"],
        }
    )
    keys = connector._resolve_space_keys()
    assert keys == ["ENG"]


def test_confluence_validate_raises_for_invalid_space_key() -> None:
    """Invalid space keys are rejected during validation."""
    from services.connectors.atlassian import ConfluenceConnector

    class NoopConnector(ConfluenceConnector):
        def _check_confluence_reachability(self) -> None:
            return None

    with pytest.raises(ValueError, match="Invalid.*space key"):
        NoopConnector(
            {"base_url": "https://wiki.local", "api_token": "t", "space_keys": ["ENG OPS"]}
        ).validate()

    with pytest.raises(ValueError, match="Invalid.*space key"):
        NoopConnector(
            {"base_url": "https://wiki.local", "api_token": "t", "space_keys": [""]}
        ).validate()

    with pytest.raises(ValueError, match="Invalid.*space key"):
        NoopConnector(
            {"base_url": "https://wiki.local", "api_token": "t", "space_key": "KEY WITH SPACES"}
        ).validate()

    # Valid space keys should pass validation
    NoopConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_keys": ["ENG"]}
    ).validate()

    NoopConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_keys": ["ENG", "OPS"]}
    ).validate()

    NoopConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_key": "ENG"}
    ).validate()


# ── Confluence MIME filter tests ────────────────────────────────────────────────


def test_mime_allowlist_allows_only_specified_types() -> None:
    """When allowlist is set, only matching MIME types pass."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "attachment_mime_allowlist": ["application/pdf", "text/plain"],
        }
    )
    assert connector._mime_is_allowed("application/pdf")
    assert connector._mime_is_allowed("text/plain")
    assert not connector._mime_is_allowed("image/png")
    assert not connector._mime_is_allowed("video/mp4")


def test_mime_empty_allowlist_allows_all() -> None:
    """Empty or missing allowlist allows all MIME types."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    assert connector._mime_is_allowed("application/pdf")
    assert connector._mime_is_allowed("video/mp4")
    assert connector._mime_is_allowed("application/octet-stream")

    connector2 = ConfluenceConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "attachment_mime_allowlist": []}
    )
    assert connector2._mime_is_allowed("application/pdf")


def test_mime_blocklist_blocks_specified_types() -> None:
    """Blocklist entries prevent specific MIME types."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "attachment_mime_blocklist": ["application/x-msdownload"],
        }
    )
    assert not connector._mime_is_allowed("application/x-msdownload")
    assert connector._mime_is_allowed("application/pdf")


def test_mime_prefix_blocklist_blocks_type_family() -> None:
    """Blocklist entries ending in / block MIME type families by prefix."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "attachment_mime_blocklist": ["video/", "audio/"],
        }
    )
    assert not connector._mime_is_allowed("video/mp4")
    assert not connector._mime_is_allowed("video/webm")
    assert not connector._mime_is_allowed("audio/mpeg")
    assert connector._mime_is_allowed("application/pdf")


def test_mime_blocklist_wins_over_allowlist() -> None:
    """Blocklist takes precedence over allowlist."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "attachment_mime_allowlist": ["application/pdf", "video/mp4"],
            "attachment_mime_blocklist": ["video/"],
        }
    )
    assert connector._mime_is_allowed("application/pdf")
    assert not connector._mime_is_allowed("video/mp4")  # blocked by prefix rule
    assert not connector._mime_is_allowed("video/webm")


# ── Streaming download tests ──────────────────────────────────────────────────


def test_streaming_download_computes_sha256_correctly() -> None:
    """Streaming download computes the correct SHA256 for attachment content."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "pat"})

    import hashlib
    import tempfile

    content = b"test attachment content for sha256 verification"
    expected_sha = hashlib.sha256(content).hexdigest()

    response = _make_fake_response(content)

    with tempfile.TemporaryDirectory() as tmpdir:
        result = connector._stream_to_file(
            response, str(Path(tmpdir) / "test.txt"), "test.txt", max_bytes=None
        )
        assert result.sha256 == expected_sha
        assert Path(result.path).read_bytes() == content


def test_streaming_download_enforces_max_size() -> None:
    """Max attachment size is enforced during streaming."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "pat"})

    content = b"x" * 100
    response = _make_fake_response(content)

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        dest = str(Path(tmpdir) / "large.txt")
        with pytest.raises(ValueError, match="exceeds maximum size"):
            connector._stream_to_file(response, dest, "large.txt", max_bytes=50)


def test_streaming_download_max_size_large_content() -> None:
    """Larger content is handled correctly when under max size."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "pat"})

    content = b"x" * 1000
    response = _make_fake_response(content)

    import hashlib
    import tempfile

    expected_sha = hashlib.sha256(content).hexdigest()

    with tempfile.TemporaryDirectory() as tmpdir:
        result = connector._stream_to_file(
            response, str(Path(tmpdir) / "ok.txt"), "ok.txt", max_bytes=2000
        )
        assert result.sha256 == expected_sha
        assert Path(result.path).read_bytes() == content


# ── Retry/backoff tests ────────────────────────────────────────────────────────


def test_backoff_seconds_produces_positive_delays() -> None:
    """_backoff_seconds returns positive values in expected range."""
    from services.connectors.atlassian import _AtlassianConnectorBase

    delay_0 = _AtlassianConnectorBase._backoff_seconds(0)
    delay_1 = _AtlassianConnectorBase._backoff_seconds(1)
    delay_5 = _AtlassianConnectorBase._backoff_seconds(5)

    assert 0.25 <= delay_0 <= 1.0  # 0.5 + jitter
    assert 0.5 <= delay_1 <= 1.5  # 1.0 + jitter
    assert 16.0 <= delay_5 <= 30.0  # capped at 30

    # With jitter, consecutive calls should differ (almost certainly)
    delays = [_AtlassianConnectorBase._backoff_seconds(0) for _ in range(100)]
    assert len(set(delays)) > 1, "backoff should include jitter"


def test_config_int_returns_default_for_missing() -> None:
    """_config_int returns default when key is missing."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    assert connector._config_int("retry_count", 3) == 3
    assert connector._config_int("request_timeout_seconds", 30) == 30
    assert connector._config_int("max_attachment_mb", 50) == 50


def test_config_int_returns_configured_value() -> None:
    """_config_int returns the configured value when present."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "retry_count": 5,
            "request_timeout_seconds": 60,
            "max_attachment_mb": 100,
        }
    )
    assert connector._config_int("retry_count", 3) == 5
    assert connector._config_int("request_timeout_seconds", 30) == 60
    assert connector._config_int("max_attachment_mb", 50) == 100


def test_effective_retry_count_default() -> None:
    """_effective_retry_count returns default when not configured."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    assert connector._effective_retry_count() == 3


def test_effective_timeout_default() -> None:
    """_effective_timeout returns default when not configured."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    assert connector._effective_timeout() == 30


def test_effective_values_from_config() -> None:
    """_effective_timeout and _effective_retry_count use config values."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "retry_count": 7,
            "request_timeout_seconds": 15,
        }
    )
    assert connector._effective_retry_count() == 7
    assert connector._effective_timeout() == 15


def test_config_list_returns_list() -> None:
    """_config_list returns proper list from config."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "space_keys": ["ENG", "OPS"],
            "attachment_mime_blocklist": ["video/", "audio/"],
        }
    )
    assert connector._config_list("space_keys") == ["ENG", "OPS"]
    assert connector._config_list("attachment_mime_blocklist") == ["video/", "audio/"]


def test_config_list_missing_returns_empty() -> None:
    """_config_list returns [] when key is missing."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    assert connector._config_list("space_keys") == []
    assert connector._config_list("attachment_mime_allowlist") == []


# ── Confluence connection validation tests ────────────────────────────────────


def test_confluence_validate_performs_reachability_check() -> None:
    """validate() performs a real API check via _check_confluence_reachability."""
    from services.connectors.atlassian import ConfluenceConnector

    class ValidatingConnector(ConfluenceConnector):
        _check_called = False

        def _check_confluence_reachability(self) -> None:
            self._check_called = True

        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            return {"key": "ENG"}

    connector = ValidatingConnector({"base_url": "https://wiki.local", "api_token": "t"})
    connector.validate()
    assert connector._check_called


def test_confluence_validate_with_space_keys_hits_specific_endpoint() -> None:
    """validate() with space_keys hits the specific space endpoint."""
    from services.connectors.atlassian import ConfluenceConnector

    captured_paths: list[str] = []

    class ValidatingConnector(ConfluenceConnector):
        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            captured_paths.append(path)
            return {"key": "ENG"}

    connector = ValidatingConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_keys": ["ENG"]}
    )
    connector.validate()
    assert any("/rest/api/space/ENG" in p for p in captured_paths)


def test_confluence_validate_without_space_keys_hits_general_endpoint() -> None:
    """validate() without space_keys hits the general space list endpoint."""
    from services.connectors.atlassian import ConfluenceConnector

    captured_paths: list[str] = []

    class ValidatingConnector(ConfluenceConnector):
        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            captured_paths.append(path)
            return {"results": [{"key": "ENG"}]}

    connector = ValidatingConnector({"base_url": "https://wiki.local", "api_token": "t"})
    connector.validate()
    assert any("/rest/api/space" in p for p in captured_paths)


# ── Confluence backward compatibility tests ──────────────────────────────────


def test_existing_confluence_sources_keep_working() -> None:
    """Existing Confluence sources with minimal config continue working."""
    from services.connectors.atlassian import ConfluenceConnector

    # Minimal config (base_url + api_token) should validate on init
    connector = ConfluenceConnector({"base_url": "https://wiki.local", "api_token": "t"})
    # Should not raise on init
    assert connector._config_str("auth_mode", "service_account") == "service_account"
    assert connector._resolve_space_keys() == []

    # Legacy space_key should still work
    connector2 = ConfluenceConnector(
        {"base_url": "https://wiki.local", "api_token": "t", "space_key": "ENG"}
    )
    assert connector2._resolve_space_keys() == ["ENG"]


# ── MIME filter behavior for different MIME types ───────────────────────────


def test_mime_filter_various_types() -> None:
    """MIME filter handles various type formats correctly."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "attachment_mime_allowlist": [
                "application/pdf",
                "text/plain",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ],
        }
    )
    assert connector._mime_is_allowed("application/pdf")
    assert connector._mime_is_allowed("text/plain")
    assert connector._mime_is_allowed(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    # Not in allowlist
    assert not connector._mime_is_allowed("image/png")
    assert not connector._mime_is_allowed("application/zip")


def test_mime_blocklist_prefix_matching() -> None:
    """Blocklist prefix matching works for 'video/', 'audio/', etc."""
    from services.connectors.atlassian import ConfluenceConnector

    connector = ConfluenceConnector(
        {
            "base_url": "https://wiki.local",
            "api_token": "t",
            "attachment_mime_blocklist": [
                "video/",
                "audio/",
                "application/x-msdownload",
            ],
        }
    )
    # Prefix matches
    assert not connector._mime_is_allowed("video/mp4")
    assert not connector._mime_is_allowed("video/x-matroska")
    assert not connector._mime_is_allowed("audio/mpeg")
    assert not connector._mime_is_allowed("audio/ogg")
    # Exact match
    assert not connector._mime_is_allowed("application/x-msdownload")
    # Not blocked
    assert connector._mime_is_allowed("application/pdf")
    assert connector._mime_is_allowed("text/plain")


# ── Jira auth_mode tests ────────────────────────────────────────────────────────


def test_jira_auth_mode_defaults_to_service_account() -> None:
    """auth_mode defaults to service_account when omitted for Jira."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    auth_mode = connector._config_str("auth_mode", "service_account")
    assert auth_mode == "service_account"


def test_jira_validate_rejects_unsupported_auth_modes() -> None:
    """Unsupported auth modes are rejected with a clear error for Jira."""
    from services.connectors.atlassian import JiraConnector

    class NoopConnector(JiraConnector):
        def _check_jira_reachability(self) -> None:
            return None

    with pytest.raises(ValueError, match="auth_mode"):
        NoopConnector(
            {"base_url": "https://jira.local", "api_token": "t", "auth_mode": "user_delegated"}
        ).validate()

    with pytest.raises(ValueError, match="auth_mode"):
        NoopConnector(
            {"base_url": "https://jira.local", "api_token": "t", "auth_mode": "oauth"}
        ).validate()

    with pytest.raises(ValueError, match="auth_mode"):
        NoopConnector(
            {"base_url": "https://jira.local", "api_token": "t", "auth_mode": ""}
        ).validate()


# ── Jira project_keys / JQL tests ──────────────────────────────────────────────


def test_jira_project_keys_omitted_uses_default_jql() -> None:
    """project_keys omitted means default all-visible-source JQL."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    jql = connector._jql()
    assert "ORDER BY updated ASC" in jql
    # No project filter when no project keys
    assert "project" not in jql.lower()


def test_jira_project_keys_empty_uses_default_jql() -> None:
    """project_keys: [] means default all-visible-source JQL."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {"base_url": "https://jira.local", "api_token": "t", "project_keys": []}
    )
    jql = connector._jql()
    assert "ORDER BY updated ASC" in jql
    assert "project" not in jql.lower()


def test_jira_project_keys_single_filter() -> None:
    """project_keys: ['ENG'] filters only ENG."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {"base_url": "https://jira.local", "api_token": "t", "project_keys": ["ENG"]}
    )
    jql = connector._jql()
    assert "project = ENG" in jql
    assert "ORDER BY updated ASC" in jql


def test_jira_project_keys_multiple_filter() -> None:
    """project_keys: ['ENG', 'OPS'] builds project IN (...) JQL."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "project_keys": ["ENG", "OPS"],
        }
    )
    jql = connector._jql()
    assert "project IN (ENG, OPS)" in jql
    assert "ORDER BY updated ASC" in jql


def test_jira_legacy_project_key_maps_to_project_keys() -> None:
    """Legacy project_key maps to project_keys single-element list."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {"base_url": "https://jira.local", "api_token": "t", "project_key": "ENG"}
    )
    keys = connector._resolve_project_keys()
    assert keys == ["ENG"]

    jql = connector._jql()
    assert "project = ENG" in jql
    assert "ORDER BY updated ASC" in jql


def test_jira_project_keys_takes_precedence_over_legacy() -> None:
    """project_keys takes precedence over legacy project_key when both set."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "project_key": "OPS",
            "project_keys": ["ENG"],
        }
    )
    keys = connector._resolve_project_keys()
    assert keys == ["ENG"]


def test_jira_custom_jql_wins_over_project_keys() -> None:
    """Custom jql wins over project_keys, project_key, and updated_since."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "project_key": "ENG",
            "updated_since": "2026-01-01 00:00",
            "jql": "project = OPS AND status = Done",
        }
    )
    jql = connector._jql()
    # JQL should be the custom one, ignoring project_key and updated_since
    assert "project = OPS" in jql
    assert "ENG" not in jql
    # ORDER BY should be appended since custom JQL doesn't have it
    assert "ORDER BY updated ASC" in jql


def test_jira_custom_jql_preserves_existing_order() -> None:
    """Custom jql that already has ORDER BY preserves it."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "jql": "project = ENG ORDER BY created DESC",
        }
    )
    jql = connector._jql()
    assert jql == "project = ENG ORDER BY created DESC"


def test_jira_jql_always_has_deterministic_ordering() -> None:
    """Default JQL always applies ORDER BY updated ASC."""
    from services.connectors.atlassian import JiraConnector

    # No project keys
    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    assert "ORDER BY updated ASC" in connector._jql()

    # With project keys
    connector2 = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "project_keys": ["ENG", "OPS"],
        }
    )
    assert "ORDER BY updated ASC" in connector2._jql()

    # With updated_since
    connector3 = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "updated_since": "2026-05-01 00:00",
        }
    )
    assert "ORDER BY updated ASC" in connector3._jql()


def test_jira_jql_with_updated_since() -> None:
    """updated_since is included in default JQL when configured."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "project_keys": ["ENG"],
            "updated_since": "2026-05-01 00:00",
        }
    )
    jql = connector._jql()
    assert 'updated >= "2026-05-01 00:00"' in jql
    assert "project = ENG" in jql
    assert "ORDER BY updated ASC" in jql


def test_jira_jql_without_project_keys_and_updated_since() -> None:
    """Default JQL without any config still produces valid JQL."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    jql = connector._jql()
    assert "ORDER BY updated ASC" in jql


def test_jira_validate_raises_for_invalid_project_key() -> None:
    """Invalid project keys are rejected during validation."""
    from services.connectors.atlassian import JiraConnector

    class NoopConnector(JiraConnector):
        def _check_jira_reachability(self) -> None:
            return None

    with pytest.raises(ValueError, match="Invalid.*project key"):
        NoopConnector(
            {"base_url": "https://jira.local", "api_token": "t", "project_keys": ["ENG OPS"]}
        ).validate()

    with pytest.raises(ValueError, match="Invalid.*project key"):
        NoopConnector(
            {"base_url": "https://jira.local", "api_token": "t", "project_keys": [""]}
        ).validate()

    with pytest.raises(ValueError, match="Invalid.*project key"):
        NoopConnector(
            {
                "base_url": "https://jira.local",
                "api_token": "t",
                "project_key": "KEY WITH SPACES",
            }
        ).validate()

    # Valid project keys should pass
    NoopConnector(
        {"base_url": "https://jira.local", "api_token": "t", "project_keys": ["ENG"]}
    ).validate()

    NoopConnector(
        {"base_url": "https://jira.local", "api_token": "t", "project_keys": ["ENG", "OPS"]}
    ).validate()

    NoopConnector(
        {"base_url": "https://jira.local", "api_token": "t", "project_key": "ENG"}
    ).validate()


# ── Jira rich metadata tests ───────────────────────────────────────────────────


def test_jira_format_people_field() -> None:
    """_format_people_field extracts safe identifiers and display fields."""
    from services.connectors.atlassian import JiraConnector

    person = {
        "key": "user123",
        "name": "jdoe",
        "displayName": "Jane Doe",
        "emailAddress": "jane@example.com",
        "active": True,
    }
    result = JiraConnector._format_people_field(person)
    assert result["key"] == "user123"
    assert result["name"] == "jdoe"
    assert result["display_name"] == "Jane Doe"
    assert result["email"] == "jane@example.com"
    assert result["active"] is True


def test_jira_format_people_field_minimal() -> None:
    """_format_people_field handles minimal fields gracefully."""
    from services.connectors.atlassian import JiraConnector

    person = {"displayName": "Alice"}
    result = JiraConnector._format_people_field(person)
    assert result["display_name"] == "Alice"
    assert "key" not in result
    assert "email" not in result


def test_jira_format_people_field_empty() -> None:
    """_format_people_field handles empty dict."""
    from services.connectors.atlassian import JiraConnector

    result = JiraConnector._format_people_field({})
    assert result == {}


def test_jira_build_issue_metadata_full() -> None:
    """_build_issue_metadata captures all rich metadata fields."""
    from services.connectors.atlassian import JiraConnector

    fields = {
        "project": {"key": "ENG", "name": "Engineering"},
        "issuetype": {"name": "Bug"},
        "status": {
            "name": "In Progress",
            "statusCategory": {"name": "In Progress"},
        },
        "priority": {"name": "High"},
        "resolution": {"name": "Fixed"},
        "labels": ["frontend", "security"],
        "components": [{"name": "API"}, {"name": "UI"}],
        "fixVersions": [{"name": "v2.0"}],
        "versions": [{"name": "v1.0"}],
        "created": "2026-01-15T10:00:00.000+0000",
        "updated": "2026-05-01T12:00:00.000+0000",
        "resolutiondate": "2026-05-01T12:30:00.000+0000",
        "assignee": {
            "key": "user1",
            "name": "alice",
            "displayName": "Alice Cohen",
            "active": True,
        },
        "reporter": {
            "key": "user2",
            "name": "bob",
            "displayName": "Bob Levi",
            "active": True,
        },
        "creator": {
            "key": "user3",
            "name": "dana",
            "displayName": "Dana Katz",
            "active": True,
        },
    }

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    metadata = connector._build_issue_metadata(key="ENG-42", fields=fields)

    assert metadata["atlassian_type"] == "jira_issue"
    assert metadata["issue_key"] == "ENG-42"
    assert metadata["project_key"] == "ENG"
    assert metadata["project_name"] == "Engineering"
    assert metadata["issuetype"] == "Bug"
    assert metadata["status"] == "In Progress"
    assert metadata["status_category"] == "In Progress"
    assert metadata["priority"] == "High"
    assert metadata["resolution"] == "Fixed"
    assert metadata["labels"] == ["frontend", "security"]
    assert metadata["components"] == ["API", "UI"]
    assert metadata["fixVersions"] == ["v2.0"]
    assert metadata["versions"] == ["v1.0"]
    assert metadata["created"] == "2026-01-15T10:00:00.000+0000"
    assert metadata["updated"] == "2026-05-01T12:00:00.000+0000"
    assert metadata["resolutiondate"] == "2026-05-01T12:30:00.000+0000"
    assert metadata["assignee"]["display_name"] == "Alice Cohen"
    assert metadata["reporter"]["display_name"] == "Bob Levi"
    assert metadata["creator"]["display_name"] == "Dana Katz"


def test_jira_build_issue_metadata_empty_fields() -> None:
    """_build_issue_metadata handles missing optional fields."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    metadata = connector._build_issue_metadata(key="ENG-1", fields={})

    assert metadata["atlassian_type"] == "jira_issue"
    assert metadata["issue_key"] == "ENG-1"
    # Optional fields should not be present
    assert "project_key" not in metadata
    assert "status" not in metadata
    assert "assignee" not in metadata
    assert "labels" not in metadata


def test_jira_build_issue_metadata_parent_and_subtasks() -> None:
    """_build_issue_metadata captures parent and subtasks."""
    from services.connectors.atlassian import JiraConnector

    fields = {
        "parent": {
            "key": "ENG-40",
            "fields": {"summary": "Parent epic"},
        },
        "subtasks": [
            {
                "key": "ENG-43",
                "fields": {
                    "summary": "Sub-task 1",
                    "status": {"name": "Done"},
                },
            },
            {
                "key": "ENG-44",
                "fields": {
                    "summary": "Sub-task 2",
                    "status": {"name": "To Do"},
                },
            },
        ],
    }

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    metadata = connector._build_issue_metadata(key="ENG-42", fields=fields)

    assert metadata["parent"]["key"] == "ENG-40"
    assert metadata["parent"]["summary"] == "Parent epic"
    assert metadata["subtasks"][0]["key"] == "ENG-43"
    assert metadata["subtasks"][1]["key"] == "ENG-44"
    assert metadata["subtasks"][0]["status"] == "Done"


def test_jira_build_issue_metadata_issuelinks() -> None:
    """_build_issue_metadata captures issue links with direction."""
    from services.connectors.atlassian import JiraConnector

    fields = {
        "issuelinks": [
            {
                "type": {"name": "Blocks"},
                "outwardIssue": {
                    "key": "ENG-50",
                    "fields": {
                        "summary": "Blocked issue",
                        "status": {"name": "To Do"},
                    },
                },
            },
            {
                "type": {"name": "Blocks"},
                "inwardIssue": {
                    "key": "ENG-45",
                    "fields": {
                        "summary": "Blocker",
                        "status": {"name": "In Progress"},
                    },
                },
            },
        ],
    }

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    metadata = connector._build_issue_metadata(key="ENG-42", fields=fields)

    links = metadata["issuelinks"]
    assert len(links) == 2
    # Outward link
    assert links[0]["direction"] == "outward"
    assert links[0]["linked_issue_key"] == "ENG-50"
    assert links[0]["linked_issue_status"] == "To Do"
    # Inward link
    assert links[1]["direction"] == "inward"
    assert links[1]["linked_issue_key"] == "ENG-45"
    assert links[1]["linked_issue_status"] == "In Progress"


def test_jira_build_issue_metadata_comments() -> None:
    """Comment metadata preserves author, created, updated, and visibility."""
    from services.connectors.atlassian import JiraConnector

    fields = {
        "comment": {
            "comments": [
                {
                    "id": "10000",
                    "author": {
                        "key": "user1",
                        "name": "alice",
                        "displayName": "Alice Cohen",
                        "active": True,
                    },
                    "updateAuthor": {
                        "key": "user2",
                        "name": "bob",
                        "displayName": "Bob Levi",
                        "active": True,
                    },
                    "body": "This is a comment.",
                    "created": "2026-01-20T10:00:00.000+0000",
                    "updated": "2026-01-21T12:00:00.000+0000",
                    "visibility": {
                        "type": "role",
                        "value": "Developers",
                    },
                },
            ]
        },
    }

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    metadata = connector._build_issue_metadata(key="ENG-42", fields=fields)

    comments = metadata["comments"]
    assert len(comments) == 1
    assert comments[0]["author"]["display_name"] == "Alice Cohen"
    assert comments[0]["update_author"]["display_name"] == "Bob Levi"
    assert comments[0]["created"] == "2026-01-20T10:00:00.000+0000"
    assert comments[0]["updated"] == "2026-01-21T12:00:00.000+0000"
    assert comments[0]["visibility"]["type"] == "role"
    assert comments[0]["visibility"]["value"] == "Developers"
    assert "body_preview" in comments[0]


def test_jira_build_issue_metadata_comments_disabled() -> None:
    """Comment metadata is not included when include_comments is False."""
    from services.connectors.atlassian import JiraConnector

    fields = {
        "comment": {
            "comments": [
                {
                    "id": "10000",
                    "author": {"displayName": "Alice"},
                    "body": "Some comment",
                },
            ]
        },
    }

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "include_comments": False,
        }
    )
    metadata = connector._build_issue_metadata(key="ENG-42", fields=fields)

    assert "comments" not in metadata


def test_jira_build_issue_metadata_restricted_comment_visibility() -> None:
    """Restricted comment visibility is captured as metadata."""
    from services.connectors.atlassian import JiraConnector

    fields = {
        "comment": {
            "comments": [
                {
                    "id": "10001",
                    "author": {"displayName": "Alice"},
                    "body": "Restricted comment",
                    "created": "2026-01-20T10:00:00.000+0000",
                    "visibility": {
                        "type": "role",
                        "value": "Administrators",
                    },
                },
            ]
        },
    }

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    metadata = connector._build_issue_metadata(key="ENG-42", fields=fields)

    comments = metadata["comments"]
    assert comments[0]["visibility"]["type"] == "role"
    assert comments[0]["visibility"]["value"] == "Administrators"
    assert "body_preview" in comments[0]


def test_jira_issue_text_rich_people_fields() -> None:
    """Issue text includes people fields with display names."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields = {
        "assignee": {"displayName": "Alice Cohen"},
        "reporter": {"displayName": "Bob Levi"},
        "creator": {"displayName": "Dana Katz"},
    }
    text = connector._issue_text(summary="People test", fields=fields)

    assert "Assignee: Alice Cohen" in text
    assert "Reporter: Bob Levi" in text
    assert "Creator: Dana Katz" in text


def test_jira_issue_text_rich_metadata_fields() -> None:
    """Issue text includes status, priority, labels, components, versions."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields = {
        "status": {"name": "In Progress"},
        "priority": {"name": "High"},
        "resolution": {"name": "Fixed"},
        "labels": ["frontend", "security"],
        "components": [{"name": "API"}, {"name": "UI"}],
        "fixVersions": [{"name": "v2.0"}],
        "versions": [{"name": "v1.0"}],
    }
    text = connector._issue_text(summary="Rich fields", fields=fields)

    assert "Status: In Progress" in text
    assert "Priority: High" in text
    assert "Resolution: Fixed" in text
    assert "Labels: frontend, security" in text
    assert "Components: API, UI" in text
    assert "Fix Versions: v2.0" in text
    assert "Affects Versions: v1.0" in text


def test_jira_issue_text_comments_inline() -> None:
    """Comments are rendered into issue text with author and timestamp."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields = {
        "comment": {
            "comments": [
                {
                    "author": {"displayName": "Alice Cohen", "name": "alice"},
                    "body": "First comment",
                    "created": "2026-01-20T10:00:00.000+0000",
                },
                {
                    "author": {"displayName": "Bob Levi"},
                    "body": "Second comment",
                    "created": "2026-01-21T12:00:00.000+0000",
                },
            ]
        },
    }
    text = connector._issue_text(summary="Comments test", fields=fields)

    assert "Comments:" in text
    assert "Alice Cohen (2026-01-20T10:00:00.000+0000):" in text
    assert "First comment" in text
    assert "Bob Levi (2026-01-21T12:00:00.000+0000):" in text
    assert "Second comment" in text


def test_jira_issue_text_comments_disabled() -> None:
    """Comments are not rendered when include_comments is False."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "include_comments": False,
        }
    )
    fields = {
        "comment": {
            "comments": [
                {
                    "author": {"displayName": "Alice"},
                    "body": "Should not appear",
                },
            ]
        },
    }
    text = connector._issue_text(summary="No comments", fields=fields)

    assert "Comments:" not in text
    assert "Should not appear" not in text


def test_jira_issue_text_parent_and_subtasks() -> None:
    """Issue text includes parent and subtasks with status."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields = {
        "parent": {
            "key": "ENG-40",
            "fields": {"summary": "Parent epic"},
        },
        "subtasks": [
            {
                "key": "ENG-43",
                "fields": {
                    "summary": "Sub-task 1",
                    "status": {"name": "Done"},
                },
            },
        ],
    }
    text = connector._issue_text(summary="Parent test", fields=fields)

    assert "Parent: ENG-40 (Parent epic)" in text
    assert "Subtasks:" in text
    assert "ENG-43" in text
    assert "Sub-task 1" in text
    assert "[Done]" in text


def test_jira_issue_text_issuelinks() -> None:
    """Issue text includes issue links with direction and status."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields = {
        "issuelinks": [
            {
                "type": {
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "outwardIssue": {
                    "key": "ENG-50",
                    "fields": {
                        "summary": "Depends on this",
                        "status": {"name": "To Do"},
                    },
                },
            },
        ],
    }
    text = connector._issue_text(summary="Links test", fields=fields)

    assert "Issue Links:" in text
    assert "blocks" in text
    assert "ENG-50" in text
    assert "Depends on this" in text
    assert "[To Do]" in text


def test_jira_issue_text_dates() -> None:
    """Issue text includes date fields."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields = {
        "created": "2026-01-15T10:00:00.000+0000",
        "updated": "2026-05-01T12:00:00.000+0000",
        "resolutiondate": "2026-05-01T12:30:00.000+0000",
    }
    text = connector._issue_text(summary="Date test", fields=fields)

    assert "Created: 2026-01-15T10:00:00.000+0000" in text
    assert "Updated: 2026-05-01T12:00:00.000+0000" in text
    assert "Resolution Date: 2026-05-01T12:30:00.000+0000" in text


# ── Jira changelog/worklog defaults tests ──────────────────────────────────────


def test_jira_changelog_default_false() -> None:
    """include_changelog defaults to False."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    assert connector._config_bool("include_changelog", False) is False


def test_jira_worklogs_default_false() -> None:
    """include_worklogs defaults to False."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    assert connector._config_bool("include_worklogs", False) is False


# ── Jira connection validation tests ───────────────────────────────────────────


def test_jira_validate_performs_reachability_check() -> None:
    """validate() performs a real API check via _check_jira_reachability."""
    from services.connectors.atlassian import JiraConnector

    class ValidatingConnector(JiraConnector):
        _check_called = False

        def _check_jira_reachability(self) -> None:
            self._check_called = True

        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            return {"name": "admin"}

    connector = ValidatingConnector({"base_url": "https://jira.local", "api_token": "t"})
    connector.validate()
    assert connector._check_called


def test_jira_validate_with_project_keys_hits_myself_and_project_endpoint() -> None:
    """validate() with project_keys hits /myself and specific project endpoint."""
    from services.connectors.atlassian import JiraConnector

    captured_paths: list[str] = []

    class ValidatingConnector(JiraConnector):
        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            captured_paths.append(path)
            if "/myself" in path:
                return {"name": "admin"}
            if "/project/" in path:
                return {"key": "ENG"}
            return {}

    connector = ValidatingConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "project_keys": ["ENG"],
        }
    )
    connector.validate()
    assert any("/rest/api/2/myself" in p for p in captured_paths)
    assert any("/rest/api/2/project/ENG" in p for p in captured_paths)


def test_jira_validate_without_project_keys_hits_myself_and_search() -> None:
    """validate() without project_keys hits /myself and general search."""
    from services.connectors.atlassian import JiraConnector

    captured_paths: list[str] = []

    class ValidatingConnector(JiraConnector):
        def _request_json(self, path: str, **_: object) -> dict[str, object]:
            captured_paths.append(path)
            if "/myself" in path:
                return {"name": "admin"}
            if "/search" in path:
                return {"issues": []}
            return {}

    connector = ValidatingConnector({"base_url": "https://jira.local", "api_token": "t"})
    connector.validate()
    assert any("/rest/api/2/myself" in p for p in captured_paths)
    assert any("/rest/api/2/search" in p for p in captured_paths)


# ── Jira existing sources backward compatibility ──────────────────────────────


def test_existing_jira_sources_keep_working() -> None:
    """Existing Jira sources with minimal config continue working."""
    from services.connectors.atlassian import JiraConnector

    # Minimal config (base_url + api_token) should work
    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    assert connector._config_str("auth_mode", "service_account") == "service_account"
    assert connector._resolve_project_keys() == []

    # Legacy project_key should still work
    connector2 = JiraConnector(
        {"base_url": "https://jira.local", "api_token": "t", "project_key": "ENG"}
    )
    assert connector2._resolve_project_keys() == ["ENG"]
    jql = connector2._jql()
    assert "project = ENG" in jql
    assert "ORDER BY updated ASC" in jql

    # Updated-since should work
    connector3 = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "project_key": "OPS",
            "updated_since": "2026-01-01 00:00",
        }
    )
    assert connector3._resolve_project_keys() == ["OPS"]
    jql = connector3._jql()
    assert "project = OPS" in jql
    assert 'updated >= "2026-01-01 00:00"' in jql


# ── Jira _jira_field_to_text tests ─────────────────────────────────────────────


def test_jira_field_to_text_handles_html() -> None:
    """_jira_field_to_text extracts text from HTML content."""
    from services.connectors.atlassian import JiraConnector

    result = JiraConnector._jira_field_to_text("<p>Hello <strong>world</strong></p>")
    assert "Hello" in result
    assert "world" in result


def test_jira_field_to_text_handles_plain_text() -> None:
    """_jira_field_to_text returns plain text unchanged."""
    from services.connectors.atlassian import JiraConnector

    result = JiraConnector._jira_field_to_text("Simple plain text")
    assert result == "Simple plain text"


def test_jira_field_to_text_handles_adf_dict() -> None:
    """_jira_field_to_text handles ADF dict with content list."""
    from services.connectors.atlassian import JiraConnector

    result = JiraConnector._jira_field_to_text(
        {
            "content": [
                {"text": "First paragraph"},
                {"content": [{"text": "Nested content"}]},
            ]
        }
    )
    assert "First paragraph" in result
    assert "Nested content" in result


def test_jira_field_to_text_handles_list() -> None:
    """_jira_field_to_text handles a list of items."""
    from services.connectors.atlassian import JiraConnector

    result = JiraConnector._jira_field_to_text([{"text": "Item 1"}, {"text": "Item 2"}])
    assert "Item 1" in result
    assert "Item 2" in result


def test_jira_field_to_text_handles_empty() -> None:
    """_jira_field_to_text handles empty/falsy values."""
    from services.connectors.atlassian import JiraConnector

    assert JiraConnector._jira_field_to_text(None) == ""
    assert JiraConnector._jira_field_to_text("") == ""
    assert JiraConnector._jira_field_to_text({}) == ""


# ── Jira attachment MIME filtering tests ──────────────────────────────────────


def test_jira_attachment_mime_filter_allows_file() -> None:
    """Jira connector respects MIME allowlist for attachments."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "attachment_mime_allowlist": ["text/plain", "application/pdf"],
        }
    )
    assert connector._mime_is_allowed("text/plain")
    assert connector._mime_is_allowed("application/pdf")
    assert not connector._mime_is_allowed("image/png")


def test_jira_attachment_mime_blocklist() -> None:
    """Jira connector respects MIME blocklist for attachments."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "attachment_mime_blocklist": ["video/"],
        }
    )
    assert not connector._mime_is_allowed("video/mp4")
    assert connector._mime_is_allowed("application/pdf")


# ── Jira fetch_attachments MIME filter integration tests ──────────────────────


def test_jira_fetch_attachments_applies_mime_filter() -> None:
    """Jira _fetch_attachments applies MIME filters before downloading."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector(
        {
            "base_url": "https://jira.local",
            "api_token": "t",
            "attachment_mime_allowlist": ["application/pdf"],
        }
    )

    fields = {
        "attachment": [
            {
                "id": "att-1",
                "filename": "doc.pdf",
                "mimeType": "application/pdf",
                "content": "https://jira.local/attachments/doc.pdf",
            },
            {
                "id": "att-2",
                "filename": "image.png",
                "mimeType": "image/png",
                "content": "https://jira.local/attachments/image.png",
            },
            {
                "id": "att-3",
                "filename": "video.mp4",
                "mimeType": "video/mp4",
                "content": "https://jira.local/attachments/video.mp4",
            },
        ],
    }

    # Only PDF should survive MIME filter, but since no download stubs, none yielded
    docs = list(connector._fetch_attachments(issue_key="ENG-1", fields=fields))
    assert len(docs) == 0


# ── Jira people fields in issue text ───────────────────────────────────────────


def test_jira_issue_text_people_with_minimal_fields() -> None:
    """People fields render display name even without other fields."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields = {
        "assignee": {"displayName": "Alice"},
        "reporter": {"displayName": "Bob"},
        "creator": {"displayName": "Charlie"},
    }
    text = connector._issue_text(summary="People", fields=fields)

    assert "Assignee: Alice" in text
    assert "Reporter: Bob" in text
    assert "Creator: Charlie" in text


def test_jira_issue_text_people_missing() -> None:
    """Missing people fields don't cause errors."""
    from services.connectors.atlassian import JiraConnector

    connector = JiraConnector({"base_url": "https://jira.local", "api_token": "t"})
    fields: dict = {}
    text = connector._issue_text(summary="No people", fields=fields)

    assert "Assignee:" not in text
    assert "Reporter:" not in text
    assert "Creator:" not in text
