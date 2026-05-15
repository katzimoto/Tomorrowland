from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from services.search.meili_backfill import BackfillService
from services.search.meili_types import SearchChunkRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_G1 = str(uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"))
_DOC_ID = str(uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001"))
_SOURCE_ID = str(uuid.UUID("cccccccc-0000-0000-0000-000000000001"))


def _mock_doc_row(
    doc_id: str = _DOC_ID,
    source_id: str = _SOURCE_ID,
) -> dict[str, Any]:
    return {
        "id": doc_id,
        "source_id": source_id,
        "source": "folder",
        "path": "/data/test.txt",
        "mime_type": "text/plain",
        "title": "Test Doc",
        "source_language": "en",
        "target_language": "en",
    }


def _mock_translation_row(text: str = "translated content") -> tuple[str, ...] | None:
    return (text,) if text else None


def _mock_group_rows(*group_ids: str) -> list[str]:
    return list(group_ids)


def _mock_provider() -> MagicMock:
    provider: MagicMock = MagicMock()
    provider.existing_chunk_checksums.return_value = {}
    return provider


def _make_engine(pages: list[list[dict[str, Any]]]) -> MagicMock:
    """Create a mock Engine that returns a connection whose execute yields *pages* of rows.

    Each call to execute() for the documents query advances through *pages*.
    Other queries (translation, group_ids) return data from *side_data*.
    """
    engine = MagicMock()
    conn = MagicMock()

    doc_results = []
    for page in pages:
        result = MagicMock()
        result.mappings.return_value = page
        doc_results.append(result)

    # First call returns documents, subsequent calls return translation/group data
    doc_result_iter = iter(doc_results)

    def execute_side_effect(stmt: Any, parameters: Any = None) -> Any:
        text = str(stmt)
        if "FROM documents" in text:
            return next(doc_result_iter, MagicMock(mappings=lambda: []))
        if "FROM document_translation_versions" in text:
            result = MagicMock()
            result.one_or_none.return_value = _mock_translation_row()
            return result
        if "FROM source_permissions" in text:
            result = MagicMock()
            result.scalars.return_value = _mock_group_rows(_G1)
            return result
        result = MagicMock()
        result.mappings.return_value = []
        return result

    conn.execute.side_effect = execute_side_effect
    engine.connect.return_value.__enter__.return_value = conn
    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("services.search.meili_backfill.chunk_text")
def test_dry_run_does_not_call_provider_write_methods(mock_chunk: MagicMock) -> None:
    mock_chunk.return_value = ["chunk a", "chunk b"]
    engine = _make_engine([[_mock_doc_row()]])
    provider = _mock_provider()

    service = BackfillService(engine, provider, dry_run=True)
    summary = service.run()

    assert summary.documents_scanned == 1
    assert summary.chunks_indexed == 2
    provider.index_batch.assert_not_called()
    provider.index.assert_not_called()


@patch("services.search.meili_backfill.chunk_text")
def test_unchanged_chunks_are_skipped(mock_chunk: MagicMock) -> None:
    mock_chunk.return_value = ["hello world"]
    engine = _make_engine([[_mock_doc_row()]])
    provider = _mock_provider()

    # Simulate that this chunk already exists with matching checksum
    record = SearchChunkRecord.from_parts(
        document_id=_DOC_ID,
        chunk_index=0,
        title="Test Doc",
        content="hello world",
        allowed_group_ids=[_G1],
    )
    provider.existing_chunk_checksums.return_value = {
        record.id: record.content_checksum,
    }

    service = BackfillService(engine, provider)
    summary = service.run()

    assert summary.chunks_skipped == 1
    assert summary.chunks_indexed == 0
    provider.index_batch.assert_not_called()


@patch("services.search.meili_backfill.chunk_text")
def test_changed_chunks_are_indexed_to_shadow(mock_chunk: MagicMock) -> None:
    mock_chunk.return_value = ["new content v2"]
    engine = _make_engine([[_mock_doc_row()]])
    provider = _mock_provider()

    # Simulate old checksum - different from what we'd compute
    provider.existing_chunk_checksums.return_value = {
        f"doc_{_DOC_ID}_chunk_0000": "oldchecksum",
    }

    service = BackfillService(engine, provider)
    summary = service.run()

    assert summary.chunks_indexed == 1
    provider.index_batch.assert_called_once()
    args, kwargs = provider.index_batch.call_args
    assert len(args[0]) == 1
    assert kwargs.get("shadow") is True


@patch("services.search.meili_backfill.chunk_text")
def test_per_document_failure_increments_count(mock_chunk: MagicMock) -> None:
    mock_chunk.side_effect = [ValueError("bad data"), ["chunk for doc2"]]
    doc1 = _mock_doc_row(doc_id=_DOC_ID)
    doc2 = _mock_doc_row(doc_id=str(uuid.UUID("dddddddd-0000-0000-0000-000000000001")))
    engine = _make_engine([[doc1, doc2]])
    provider = _mock_provider()

    service = BackfillService(engine, provider)
    summary = service.run()

    assert summary.documents_scanned == 2
    assert summary.documents_failed == 1
    assert summary.chunks_indexed == 1


@patch("services.search.meili_backfill.chunk_text")
def test_summary_counts_mixed(mock_chunk: MagicMock) -> None:
    # Doc 1: 2 chunks, both new
    # Doc 2: 1 chunk, already indexed (skip)
    # Doc 3: no translation (skip)
    mock_chunk.side_effect = [
        ["chunk a", "chunk b"],
        ["chunk c"],
    ]

    doc1 = _mock_doc_row(doc_id=_DOC_ID)
    doc2 = _mock_doc_row(doc_id=str(uuid.UUID("dddddddd-0000-0000-0000-000000000001")))
    doc3 = _mock_doc_row(doc_id=str(uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")))
    engine = _make_engine([[doc1, doc2, doc3]])

    # Override the translation mock to return None for doc3
    original_execute = engine.connect.return_value.__enter__.return_value.execute

    def execute_with_no_translation_for_doc3(stmt: Any, parameters: Any = None) -> Any:
        text = str(stmt)
        if "FROM document_translation_versions" in text and "eeeeeeee" in str(parameters):
            result: MagicMock = MagicMock()
            result.one_or_none.return_value = None
            return result
        return original_execute(stmt, parameters)

    engine.connect.return_value.__enter__.return_value.execute = (
        execute_with_no_translation_for_doc3
    )

    provider = _mock_provider()
    # Pre-populate checksum for doc2 chunk
    record_doc2 = SearchChunkRecord.from_parts(
        document_id=str(uuid.UUID("dddddddd-0000-0000-0000-000000000001")),
        chunk_index=0,
        title="Test Doc",
        content="chunk c",
        allowed_group_ids=[_G1],
    )
    provider.existing_chunk_checksums.side_effect = [
        {},  # doc1: no existing chunks
        {record_doc2.id: record_doc2.content_checksum},  # doc2: already indexed
    ]

    service = BackfillService(engine, provider)
    summary = service.run()

    assert summary.documents_scanned == 3
    assert summary.documents_skipped_no_translation == 1
    assert summary.chunks_skipped == 1
    assert summary.chunks_indexed == 2
    assert summary.documents_failed == 0


@patch("services.search.meili_backfill.chunk_text")
def test_batch_size_is_respected(mock_chunk: MagicMock) -> None:
    mock_chunk.return_value = [f"chunk {i}" for i in range(5)]
    engine = _make_engine([[_mock_doc_row()]])
    provider = _mock_provider()

    service = BackfillService(engine, provider, batch_size=2)
    summary = service.run()

    assert summary.chunks_indexed == 5
    # 5 chunks with batch_size=2 => 3 batches (2 + 2 + 1)
    assert provider.index_batch.call_count == 3

    # Verify each batch respects the size limit
    calls = provider.index_batch.call_args_list
    assert len(calls[0][0][0]) == 2
    assert len(calls[1][0][0]) == 2
    assert len(calls[2][0][0]) == 1


@patch("services.search.meili_backfill.chunk_text")
def test_no_documents_returns_empty_summary(mock_chunk: MagicMock) -> None:
    engine = _make_engine([[]])
    provider = _mock_provider()

    service = BackfillService(engine, provider)
    summary = service.run()

    assert summary.documents_scanned == 0
    assert summary.chunks_indexed == 0
    assert summary.documents_failed == 0
