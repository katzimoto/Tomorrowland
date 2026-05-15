from __future__ import annotations

import hashlib

import pytest

from services.search.meili_types import (
    ChunkMetadata,
    ChunkPosition,
    SearchChunkRecord,
    build_metadata_text,
    chunk_record_id,
)

# ---------------------------------------------------------------------------
# chunk_record_id
# ---------------------------------------------------------------------------


def test_chunk_record_id_format() -> None:
    assert chunk_record_id("abc123", 4) == "doc_abc123_chunk_0004"


def test_chunk_record_id_zero_padded() -> None:
    assert chunk_record_id("x", 0) == "doc_x_chunk_0000"
    assert chunk_record_id("x", 999) == "doc_x_chunk_0999"
    assert chunk_record_id("x", 10000) == "doc_x_chunk_10000"


def test_chunk_record_id_is_deterministic() -> None:
    assert chunk_record_id("doc-1", 7) == chunk_record_id("doc-1", 7)


def test_chunk_record_id_different_inputs_differ() -> None:
    assert chunk_record_id("doc-1", 0) != chunk_record_id("doc-1", 1)
    assert chunk_record_id("doc-1", 0) != chunk_record_id("doc-2", 0)


# ---------------------------------------------------------------------------
# build_metadata_text
# ---------------------------------------------------------------------------


def test_metadata_text_includes_allowlisted_fields() -> None:
    meta = ChunkMetadata(
        file_name="report.pdf",
        author="Alice",
        owner="Bob",
        tags=["finance", "q4"],
        labels=["confidential"],
        topics=["revenue"],
        project="proj-a",
        workspace="ws-1",
        collection="col-x",
    )
    text = build_metadata_text(meta)
    assert "report.pdf" in text
    assert "Alice" in text
    assert "Bob" in text
    assert "finance" in text
    assert "q4" in text
    assert "confidential" in text
    assert "revenue" in text
    assert "proj-a" in text
    assert "ws-1" in text
    assert "col-x" in text


def test_metadata_text_excludes_sensitive_fields() -> None:
    meta = ChunkMetadata(
        path="/internal/files/secret.pdf",
        url="https://internal.example.com/doc",
        checksum="sha256:abc123",
        version="v1.2.3",
        mime_type="application/pdf",
        file_extension="pdf",
    )
    text = build_metadata_text(meta)
    assert "/internal/files" not in text
    assert "https://internal" not in text
    assert "sha256" not in text
    assert "v1.2.3" not in text
    assert "application/pdf" not in text
    assert text == "" or text.strip() == ""


def test_metadata_text_empty_for_blank_metadata() -> None:
    assert build_metadata_text(ChunkMetadata()) == ""


def test_metadata_text_space_separated() -> None:
    meta = ChunkMetadata(file_name="a.pdf", author="Bob")
    text = build_metadata_text(meta)
    assert " " in text
    parts = text.split()
    assert "a.pdf" in parts
    assert "Bob" in parts


# ---------------------------------------------------------------------------
# SearchChunkRecord — security invariant
# ---------------------------------------------------------------------------


def test_record_rejects_empty_allowed_group_ids_when_not_admin_only() -> None:
    with pytest.raises(ValueError, match="allowed_group_ids"):
        SearchChunkRecord(
            id="doc_x_chunk_0000",
            document_id="x",
            chunk_index=0,
            title="T",
            content="C",
            allowed_group_ids=[],   # empty — must be rejected
            is_admin_only=False,
            content_checksum="abc",
            indexed_at="2024-01-01T00:00:00+00:00",
            position=ChunkPosition(chunk_index=0),
        )


def test_record_allows_empty_group_ids_when_admin_only() -> None:
    # Admin-only documents may have no group IDs — that's correct
    record = SearchChunkRecord(
        id="doc_x_chunk_0000",
        document_id="x",
        chunk_index=0,
        title="T",
        content="C",
        allowed_group_ids=[],
        is_admin_only=True,
        content_checksum="abc",
        indexed_at="2024-01-01T00:00:00+00:00",
        position=ChunkPosition(chunk_index=0),
    )
    assert record.is_admin_only is True


def test_record_accepts_valid_group_ids() -> None:
    record = SearchChunkRecord(
        id="doc_x_chunk_0000",
        document_id="x",
        chunk_index=0,
        title="T",
        content="C",
        allowed_group_ids=["group-1"],
        is_admin_only=False,
        content_checksum="abc",
        indexed_at="2024-01-01T00:00:00+00:00",
        position=ChunkPosition(chunk_index=0),
    )
    assert record.allowed_group_ids == ["group-1"]


# ---------------------------------------------------------------------------
# SearchChunkRecord.from_parts — factory
# ---------------------------------------------------------------------------


def test_from_parts_sets_id_correctly() -> None:
    record = SearchChunkRecord.from_parts(
        document_id="doc-abc",
        chunk_index=3,
        title="Title",
        content="Content",
        allowed_group_ids=["g1"],
    )
    assert record.id == "doc_doc-abc_chunk_0003"


def test_from_parts_computes_content_checksum() -> None:
    content = "Hello, world."
    record = SearchChunkRecord.from_parts(
        document_id="d",
        chunk_index=0,
        title="T",
        content=content,
        allowed_group_ids=["g"],
    )
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert record.content_checksum == expected


def test_from_parts_sets_indexed_at() -> None:
    record = SearchChunkRecord.from_parts(
        document_id="d",
        chunk_index=0,
        title="T",
        content="C",
        allowed_group_ids=["g"],
    )
    # indexed_at must be a non-empty ISO 8601 string
    assert record.indexed_at
    assert "T" in record.indexed_at  # ISO 8601 datetime separator


def test_from_parts_builds_metadata_text_automatically() -> None:
    meta = ChunkMetadata(file_name="report.pdf", author="Alice")
    record = SearchChunkRecord.from_parts(
        document_id="d",
        chunk_index=0,
        title="T",
        content="C",
        allowed_group_ids=["g"],
        metadata=meta,
    )
    assert "report.pdf" in record.metadata_text
    assert "Alice" in record.metadata_text


def test_from_parts_is_deterministic_for_same_inputs() -> None:
    kwargs = dict(
        document_id="d",
        chunk_index=0,
        title="T",
        content="C",
        allowed_group_ids=["g"],
    )
    r1 = SearchChunkRecord.from_parts(**kwargs)
    r2 = SearchChunkRecord.from_parts(**kwargs)
    assert r1.id == r2.id
    assert r1.content_checksum == r2.content_checksum
