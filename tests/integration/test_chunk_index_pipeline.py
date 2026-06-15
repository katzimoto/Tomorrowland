"""Integration test: chunk_index is non-null in Qdrant payload after indexing.

Exercises PipelineWorker.process_document directly (no HTTP layer) so the
upsert_chunks call can be inspected without requiring a running Qdrant service.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from sqlalchemy import Engine

from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.pipeline.worker import PipelineWorker
from services.search.encoder import TextEncoder
from services.search.qdrant import QdrantSearchClient
from services.translation.provider import TranslationProvider
from tests.integration.test_pipeline import (
    _create_folder_source,
    _setup_admin,
)


def _make_encoder(dimension: int = 384) -> TextEncoder:
    """Return a deterministic stub that returns unit vectors of *dimension*."""
    enc = MagicMock(spec=TextEncoder)
    enc.encode.side_effect = lambda text: [0.1] * dimension
    enc.encode_batch.side_effect = lambda texts: [[0.1] * dimension for _ in texts]
    return enc


def _create_source_and_document(
    engine: Engine,
    tmp_path: Path,
) -> tuple[str, UUID]:
    """Return (source_id_hex, document_id) for a minimal folder source + document."""
    _setup_admin(engine)
    source_folder = tmp_path / "source"
    source_folder.mkdir()
    source_id_hex = _create_folder_source(engine, source_folder)
    source_id = UUID(source_id_hex)

    doc_id = uuid4()
    with engine.begin() as conn:
        repo = DocumentRepository(conn)
        doc = repo.create(
            source_id=source_id,
            external_id="fixture-doc-001",
            source="folder",  # type: ignore[arg-type]
            mime_type="text/plain",
            title="Fixture Document",
            source_language="en",
        )
        assert doc is not None
        doc_id = doc.id

    return source_id_hex, doc_id


def test_chunk_index_is_non_null_in_qdrant_payload(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """Every Qdrant point payload must carry chunk_index as a non-null integer.

    This test drives PipelineWorker.process_document with pre_extracted_text so
    the chunker produces at least one chunk, then inspects the upsert_chunks call
    to assert that chunk_index is populated on every chunk dict.
    """
    _source_id_hex, doc_id = _create_source_and_document(migrated_engine, tmp_path)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=TranslationProvider)
    mock_translator.translate.side_effect = lambda text, **_: text

    with migrated_engine.connect() as conn:
        doc_repo = DocumentRepository(conn)
        worker = PipelineWorker(
            document_repository=doc_repo,
            extractor_registry=ExtractorRegistry(),
            translator=mock_translator,
            encoder=_make_encoder(),
            qdrant_client=mock_qdrant,
        )
        worker.process_document(
            doc_id,
            pre_extracted_text=(
                "This is the first sentence of the fixture document. "
                "It contains enough text to produce at least one chunk. "
                "The pipeline should assign a chunk_index to every Qdrant point."
            ),
        )

    assert mock_qdrant.upsert_chunks.called, "upsert_chunks was never called"

    all_chunks: list[dict] = []
    for call in mock_qdrant.upsert_chunks.call_args_list:
        chunks_arg = call.args[0] if call.args else call.kwargs.get("chunks", [])
        all_chunks.extend(chunks_arg)

    assert len(all_chunks) >= 1, "Expected at least one chunk to be indexed"
    for chunk in all_chunks:
        assert "chunk_index" in chunk, f"chunk missing chunk_index: {chunk}"
        assert chunk["chunk_index"] is not None, f"chunk_index is None: {chunk}"
        assert isinstance(chunk["chunk_index"], int), (
            f"chunk_index must be int, got {type(chunk['chunk_index'])}: {chunk}"
        )
