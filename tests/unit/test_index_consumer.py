from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from services.pipeline.index_worker import IndexConsumer
from services.search.meili_types import ChunkMetadata, SearchChunkRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_rabbit() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_job_repo() -> MagicMock:
    repo = MagicMock()
    repo.mark_running_stage.return_value = None
    repo.commit.return_value = None
    repo.mark_succeeded.return_value = None
    return repo


@pytest.fixture
def mock_doc_repo() -> MagicMock:
    repo = MagicMock()
    doc = MagicMock()
    doc.id = uuid4()
    doc.title = "Test Document"
    doc.mime_type = "text/plain"
    doc.source = "folder"
    doc.source_language = "en"
    doc.target_language = "en"
    doc.translation_quality = None
    doc.source_id = uuid4()
    repo.get_by_id.return_value = doc
    repo.source_group_ids.return_value = ["group-1"]
    return repo


@pytest.fixture
def mock_publisher() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_meili() -> MagicMock:
    return MagicMock()


@pytest.fixture
def consumer(
    mock_rabbit: MagicMock,
    mock_job_repo: MagicMock,
    mock_doc_repo: MagicMock,
    mock_publisher: MagicMock,
    mock_meili: MagicMock,
) -> IndexConsumer:
    return IndexConsumer(
        rabbit=mock_rabbit,
        job_repo=mock_job_repo,
        doc_repo=mock_doc_repo,
        publisher=mock_publisher,
        meili=mock_meili,
        embedding_max_tokens=1024,
    )


# ---------------------------------------------------------------------------
# Constructor — does not require es_client
# ---------------------------------------------------------------------------


def test_constructor_accepts_required_params_only(
    mock_rabbit: MagicMock,
    mock_job_repo: MagicMock,
    mock_doc_repo: MagicMock,
    mock_publisher: MagicMock,
    mock_meili: MagicMock,
) -> None:
    """IndexConsumer must not require an es_client parameter."""
    c = IndexConsumer(
        rabbit=mock_rabbit,
        job_repo=mock_job_repo,
        doc_repo=mock_doc_repo,
        publisher=mock_publisher,
        meili=mock_meili,
        embedding_max_tokens=512,
    )
    assert c._meili is mock_meili
    assert not hasattr(c, "_es")


# ---------------------------------------------------------------------------
# handle_message — Meilisearch indexing
# ---------------------------------------------------------------------------


def test_handle_message_with_content_text_indexes_via_meili(
    consumer: IndexConsumer,
    mock_doc_repo: MagicMock,
    mock_meili: MagicMock,
    mock_job_repo: MagicMock,
    mock_publisher: MagicMock,
) -> None:
    """When content_text is present, handle_message must call _index_meili
    (which in turn calls meili.index_batch)."""
    doc_id = uuid4()
    source_id = uuid4()

    consumer.handle_message(
        job_id=uuid4(),
        document_id=doc_id,
        source_id=source_id,
        attempt=1,
        correlation_id="corr-1",
        content_text="Some document content that will be chunked.",
        translated_text="",
    )

    # Meilisearch should have been called
    assert mock_meili.index_batch.called

    # Job lifecycle
    mock_job_repo.mark_running_stage.assert_called_once()
    mock_job_repo.commit.assert_called_once()
    mock_job_repo.mark_succeeded.assert_called_once()
    mock_doc_repo.update_indexed.assert_called_once()

    # Publisher calls
    mock_publisher.publish_intelligence.assert_called_once()
    mock_publisher.publish_alert.assert_called_once()


def test_handle_message_without_content_text_skips_meili(
    consumer: IndexConsumer,
    mock_meili: MagicMock,
    mock_job_repo: MagicMock,
    mock_publisher: MagicMock,
) -> None:
    """When content_text is empty, handle_message must skip Meilisearch
    but still complete the job lifecycle."""
    doc_id = uuid4()
    source_id = uuid4()

    consumer.handle_message(
        job_id=uuid4(),
        document_id=doc_id,
        source_id=source_id,
        attempt=1,
        correlation_id="corr-2",
        content_text="",
        translated_text="",
    )

    mock_meili.index_batch.assert_not_called()
    mock_job_repo.mark_running_stage.assert_called_once()
    mock_job_repo.commit.assert_called_once()
    mock_job_repo.mark_succeeded.assert_called_once()
    mock_publisher.publish_intelligence.assert_called_once()
    mock_publisher.publish_alert.assert_called_once()


def test_handle_message_raises_when_document_not_found(
    consumer: IndexConsumer,
    mock_doc_repo: MagicMock,
) -> None:
    """handle_message must raise ValueError if the document is not found."""
    mock_doc_repo.get_by_id.return_value = None

    with pytest.raises(ValueError, match="not found"):
        consumer.handle_message(
            job_id=uuid4(),
            document_id=uuid4(),
            source_id=uuid4(),
            attempt=1,
            correlation_id="corr-3",
            content_text="some text",
        )


# ---------------------------------------------------------------------------
# _index_meili — chunk building and batch indexing
# ---------------------------------------------------------------------------


def test_index_meili_builds_chunk_records_and_calls_index_batch(
    consumer: IndexConsumer,
    mock_meili: MagicMock,
) -> None:
    """_index_meili must chunk text, build SearchChunkRecords, and call
    meili.index_batch with the records."""
    doc_id = uuid4()
    doc = MagicMock()
    doc.title = "Doc Title"
    doc.source_id = uuid4()
    doc.source = "folder"
    doc.mime_type = "application/pdf"
    doc.source_language = "en"
    doc.target_language = "fr"

    content_text = "Sentence one. Sentence two. Sentence three. " * 10
    translated_text = "Phrase un. Phrase deux. Phrase trois. " * 10
    allowed_group_ids = ["group-a", "group-b"]

    consumer._index_meili(
        document_id=doc_id,
        doc=doc,
        content_text=content_text,
        translated_text=translated_text,
        allowed_group_ids=allowed_group_ids,
    )

    mock_meili.index_batch.assert_called_once()
    records: list[SearchChunkRecord] = mock_meili.index_batch.call_args[0][0]

    assert len(records) >= 1
    for rec in records:
        assert rec.document_id == str(doc_id)
        assert isinstance(rec.chunk_index, int)
        assert rec.chunk_index >= 0
        assert rec.title == "Doc Title"
        assert doc.source_id is not None
        assert str(doc.source_id) in repr(rec)
        assert rec.allowed_group_ids == allowed_group_ids
        assert rec.metadata is not None
        assert isinstance(rec.metadata, ChunkMetadata)


def test_index_meili_without_translated_text(
    consumer: IndexConsumer,
    mock_meili: MagicMock,
) -> None:
    """When translated_text is empty, content_en must be None on all records."""
    doc_id = uuid4()
    doc = MagicMock()
    doc.title = "Title"
    doc.source_id = uuid4()
    doc.source = "folder"
    doc.mime_type = "text/plain"
    doc.source_language = "en"
    doc.target_language = "en"

    content_text = "Just one sentence here. "
    allowed_group_ids = ["group-1"]

    consumer._index_meili(
        document_id=doc_id,
        doc=doc,
        content_text=content_text,
        translated_text="",
        allowed_group_ids=allowed_group_ids,
    )

    mock_meili.index_batch.assert_called_once()
    records: list[SearchChunkRecord] = mock_meili.index_batch.call_args[0][0]

    assert len(records) >= 1
    for rec in records:
        assert rec.content_en is None


def test_index_meili_skips_index_batch_when_no_chunks(
    consumer: IndexConsumer,
    mock_meili: MagicMock,
) -> None:
    """When chunk_text produces zero chunks (empty content), index_batch
    must not be called."""
    doc_id = uuid4()
    doc = MagicMock()
    doc.title = "Title"
    doc.source_id = uuid4()
    doc.source = "folder"
    doc.mime_type = "text/plain"
    doc.source_language = "en"
    doc.target_language = "en"

    content_text = ""
    allowed_group_ids = ["group-1"]

    consumer._index_meili(
        document_id=doc_id,
        doc=doc,
        content_text=content_text,
        translated_text="",
        allowed_group_ids=allowed_group_ids,
    )

    mock_meili.index_batch.assert_not_called()


# ---------------------------------------------------------------------------
# No es_client references anywhere
# ---------------------------------------------------------------------------


def test_no_elasticsearch_imports_in_module() -> None:
    """The index_worker module must not import ElasticsearchSearchClient."""
    import importlib

    import services.pipeline.index_worker as iw

    importlib.reload(iw)
    with open(iw.__file__) as f:
        source = f.read()
    assert "elastic" not in source.lower(), "index_worker should not reference Elasticsearch"
