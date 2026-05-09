"""Unit tests for the connectors package."""

from __future__ import annotations

import json
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


def test_nifi_connector_validate_is_noop() -> None:
    NiFiConnector({}).validate()  # must not raise


def test_nifi_connector_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        list(NiFiConnector({}).fetch_documents())


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
