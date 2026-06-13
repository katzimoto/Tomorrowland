from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from services.preview.artifact_store import PreviewArtifactStore


def test_write_and_resolve_roundtrip(tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    files = store.write_artifacts(
        doc_id, "abc123", {"body-html": ("body.html", "text/html", b"<p>hi</p>")}
    )
    assert files == {"body-html": "body.html"}
    resolved = store.resolve(doc_id, "abc123", "body.html")
    assert resolved is not None
    assert resolved.read_bytes() == b"<p>hi</p>"
    assert resolved.is_relative_to(tmp_path / "previews")


def test_resolve_missing_file_returns_none(tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    assert store.resolve(uuid4(), "abc123", "body.html") is None


def test_resolve_rejects_traversal(tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    store.write_artifacts(doc_id, "abc123", {"a": ("body.txt", "text/plain", b"x")})
    assert store.resolve(doc_id, "abc123", "../../../secret.txt") is None


def test_write_rejects_escaping_filename(tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.write_artifacts(uuid4(), "abc123", {"a": ("../escape.txt", "text/plain", b"x")})


def test_invalid_sha_segment_rejected(tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.write_artifacts(uuid4(), "../escape", {"a": ("b.txt", "text/plain", b"x")})


def test_delete_is_idempotent(tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    store.write_artifacts(doc_id, "abc123", {"a": ("body.txt", "text/plain", b"x")})
    store.delete(doc_id, "abc123")
    assert store.resolve(doc_id, "abc123", "body.txt") is None
    store.delete(doc_id, "abc123")  # second delete must not raise


def test_empty_sha_uses_nosha_segment(tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    store.write_artifacts(doc_id, "", {"a": ("body.txt", "text/plain", b"x")})
    assert store.resolve(doc_id, "", "body.txt") is not None
