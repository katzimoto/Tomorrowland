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


def test_confluence_connector_fetches_pages_and_attachments() -> None:
    from services.connectors.atlassian import ConfluenceConnector, _DownloadedAttachment

    class StubConfluenceConnector(ConfluenceConnector):
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

        def _download_attachment(self, download_url: str, filename: str) -> _DownloadedAttachment:
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

        def _download_attachment(self, download_url: str, filename: str) -> _DownloadedAttachment:
            assert download_url.endswith("/error.log")
            assert filename == "error.log"
            return _DownloadedAttachment(path="/tmp/error.log", sha256="c" * 64)

    docs = list(
        StubJiraConnector(
            {"base_url": "https://jira.local", "api_token": "t", "project_key": "ENG"}
        ).fetch_documents()
    )

    assert [doc.external_id for doc in docs] == ["jira:ENG-7", "jira:ENG-7:att:10001"]
    assert docs[0].text_content == "Fix sync\n\nDetails\n\nLooks good"
    assert docs[1].path == "/tmp/error.log"
    assert docs[1].mime_type == "text/plain"


def test_atlassian_request_json_uses_basic_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as json_module
    from typing import Any

    import services.connectors.atlassian as atlassian
    from services.connectors.atlassian import JiraConnector

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json_module.dumps({"ok": True}).encode()

    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeResponse()

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

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"attachment-bytes"

    captured: dict[str, str] = {}

    def fake_urlopen(request: Any, timeout: int) -> FakeResponse:
        assert timeout == 30
        captured["url"] = request.full_url
        captured["auth"] = request.headers["Authorization"]
        return FakeResponse()

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

    assert connector._jql() == "project = OPS"
    assert (
        connector._issue_text(
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
        == "ADF issue\n\nNested text\nSecond block"
    )


def test_confluence_connector_paginates_pages() -> None:
    from services.connectors.atlassian import ConfluenceConnector

    class StubConfluenceConnector(ConfluenceConnector):
        def __init__(self) -> None:
            super().__init__({"base_url": "https://wiki.local", "api_token": "t"})
            self.starts: list[int] = []

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
            self, *, page_id: str, page_title: str
        ) -> Iterator[ConnectorDocument]:
            assert page_id
            assert page_title
            return iter(())

    connector = StubConfluenceConnector()

    docs = list(connector.fetch_documents())

    assert len(docs) == 51
    assert connector.starts == [0, 50]
