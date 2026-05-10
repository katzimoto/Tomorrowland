"""Unit tests for NiFi event parsing and connector normalization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from services.connectors.nifi import NiFiConnector, NiFiEventError, parse_nifi_event


def _event(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "source_id": str(uuid4()),
        "external_id": "flow-file-1",
        "title": "Report",
        "mime_type": "text/plain",
        "source_language": "en",
        "metadata": {"department": "finance"},
        "event_timestamp": "2026-05-10T00:00:00Z",
        "correlation_id": "corr-1",
        "payload": {"type": "inline_text", "text": "hello"},
    }
    data.update(overrides)
    return data


def test_parse_nifi_event_accepts_required_and_optional_fields() -> None:
    event = parse_nifi_event(json.dumps(_event(filename="report.txt")))

    assert event.external_id == "flow-file-1"
    assert event.display_title == "Report"
    assert event.payload.type == "inline_text"
    assert event.metadata["department"] == "finance"


def test_parse_nifi_event_rejects_malformed_json() -> None:
    with pytest.raises(NiFiEventError, match="Malformed"):
        parse_nifi_event(b"{not-json")


def test_parse_nifi_event_requires_source_and_title() -> None:
    data = _event(title=None, source_id=None)

    with pytest.raises(NiFiEventError, match="Invalid"):
        parse_nifi_event(data)


def test_parse_nifi_event_rejects_invalid_payload_strategy() -> None:
    data = _event(payload={"type": "inline_text"})

    with pytest.raises(NiFiEventError, match="Invalid"):
        parse_nifi_event(data)


def test_nifi_connector_validate_staging_root(tmp_path: Path) -> None:
    NiFiConnector({"staging_root": str(tmp_path)}).validate()

    with pytest.raises(ValueError, match="does not exist"):
        NiFiConnector({"staging_root": str(tmp_path / "missing")}).validate()


def test_nifi_connector_normalizes_inline_text() -> None:
    text = "pre-extracted text"
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    event = parse_nifi_event(_event(payload={"type": "inline_text", "text": text}, sha256=sha256))

    document = NiFiConnector({"source_id": str(event.source_id)}).normalize_event(event)

    assert document.external_id == "nifi:flow-file-1"
    assert document.title == "Report"
    assert document.mime_type == "text/plain"
    assert document.text_content == text
    assert document.path is None
    assert document.metadata["nifi_payload_type"] == "inline_text"
    assert document.metadata["department"] == "finance"


def test_nifi_connector_normalizes_staged_file(tmp_path: Path) -> None:
    staged = tmp_path / "flow-file.txt"
    staged.write_text("from staged file")
    sha256 = hashlib.sha256(staged.read_bytes()).hexdigest()
    event = parse_nifi_event(
        _event(payload={"type": "staged_file", "path": str(staged)}, sha256=sha256)
    )

    document = NiFiConnector({"staging_root": str(tmp_path)}).normalize_event(event)

    assert document.path == str(staged.resolve())
    assert document.text_content is None
    assert document.sha256 == sha256


def test_nifi_connector_rejects_staged_file_without_staging_root(tmp_path: Path) -> None:
    staged = tmp_path / "flow-file.txt"
    staged.write_text("secret")
    event = parse_nifi_event(_event(payload={"type": "staged_file", "path": str(staged)}))

    with pytest.raises(NiFiEventError, match="staging_root to be configured"):
        NiFiConnector({}).normalize_event(event)


def test_nifi_connector_rejects_staged_file_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-nifi.txt"
    outside.write_text("secret")
    event = parse_nifi_event(_event(payload={"type": "staged_file", "path": str(outside)}))

    with pytest.raises(NiFiEventError, match="outside staging_root"):
        NiFiConnector({"staging_root": str(tmp_path)}).normalize_event(event)


def test_nifi_connector_rejects_checksum_mismatch() -> None:
    event = parse_nifi_event(_event(sha256="0" * 64))

    with pytest.raises(NiFiEventError, match="checksum mismatch"):
        NiFiConnector({}).normalize_event(event)
