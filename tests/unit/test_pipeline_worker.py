from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from services.documents.models import DocumentRow
from services.pipeline.worker import PipelineWorker, ProcessResult


class _FakeDocumentRepository:
    def __init__(self, doc: DocumentRow, group_ids: list[UUID]) -> None:
        self._doc = doc
        self._group_ids = group_ids
        self.indexed_updates: list[tuple[UUID, str, str | None]] = []
        self.status_updates: list[tuple[UUID, str]] = []

    def get_by_id(self, doc_id: UUID) -> DocumentRow | None:
        return self._doc if doc_id == self._doc.id else None

    def source_group_ids(self, source_id: UUID) -> list[UUID]:
        assert source_id == self._doc.source_id
        return self._group_ids

    def update_indexed(
        self,
        doc_id: UUID,
        status: str,
        translation_quality: str | None,
    ) -> None:
        self.indexed_updates.append((doc_id, status, translation_quality))

    def update_status(self, doc_id: UUID, status: str) -> None:
        self.status_updates.append((doc_id, status))


class _FakeExtractor:
    def extract(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("pre_extracted_text should bypass extraction")


class _FakeTranslator:
    def __init__(self, translated: str | None = None) -> None:
        self._translated = translated

    def translate(self, text: str, *, source_lang: str | None = None) -> str:
        assert source_lang == "en"
        return self._translated if self._translated is not None else text


class _FakeEncoder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def encode(self, text: str) -> list[float]:
        self.calls.append(text)
        if self.fail:
            raise RuntimeError("raw_chunk_marker")
        return [0.1, 0.2, 0.3]


class _FakeElasticsearch:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict[str, object]]] = []

    def index_document(self, doc_id: str, body: dict[str, object]) -> None:
        self.calls.append((doc_id, body))
        if self.fail:
            raise RuntimeError("elasticsearch_unavailable")


class _FakeQdrant:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[dict[str, object]]] = []

    def upsert_chunks(self, chunks: list[dict[str, object]]) -> None:
        self.calls.append(chunks)
        if self.fail:
            raise RuntimeError("qdrant_unavailable")


def _document() -> DocumentRow:
    now = datetime.now(UTC)
    return DocumentRow(
        id=uuid4(),
        source_id=uuid4(),
        external_id="test:doc",
        source="folder",
        path=None,
        mime_type="text/plain",
        title="Test document",
        source_language="en",
        target_language="en",
        translation_quality=None,
        status="pending",
        content_sha256="abc",
        metadata={"safe": "metadata"},
        created_at=now,
        updated_at=now,
    )


def _worker(
    *,
    repo: _FakeDocumentRepository,
    encoder: _FakeEncoder,
    es: _FakeElasticsearch,
    qdrant: _FakeQdrant,
    translator: _FakeTranslator | None = None,
) -> PipelineWorker:
    return PipelineWorker(
        document_repository=repo,  # type: ignore[arg-type]
        extractor_registry=_FakeExtractor(),  # type: ignore[arg-type]
        translator=translator or _FakeTranslator(),  # type: ignore[arg-type]
        encoder=encoder,  # type: ignore[arg-type]
        es_client=es,  # type: ignore[arg-type]
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )


def test_worker_indexes_text_when_encoder_fails(caplog: pytest.LogCaptureFixture) -> None:
    doc = _document()
    group_id = uuid4()
    repo = _FakeDocumentRepository(doc, [group_id])
    encoder = _FakeEncoder(fail=True)
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant)

    caplog.set_level(logging.ERROR, logger="services.pipeline.worker")

    worker.process_document(doc.id, pre_extracted_text="raw_document_marker")

    assert len(es.calls) == 1
    indexed_body = es.calls[0][1]
    assert indexed_body["allowed_group_ids"] == [str(group_id)]
    assert qdrant.calls == []
    assert repo.indexed_updates == [(doc.id, "indexed", None)]
    assert repo.status_updates == []
    assert "Vector indexing failed" in caplog.text
    assert "raw_chunk_marker" not in caplog.text
    assert "raw_document_marker" not in caplog.text


def test_worker_does_not_vector_index_when_text_index_fails() -> None:
    doc = _document()
    repo = _FakeDocumentRepository(doc, [uuid4()])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch(fail=True)
    qdrant = _FakeQdrant()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant)

    with pytest.raises(RuntimeError, match="elasticsearch_unavailable"):
        worker.process_document(doc.id, pre_extracted_text="document body")

    assert encoder.calls == []
    assert qdrant.calls == []
    assert repo.indexed_updates == []
    assert repo.status_updates == [(doc.id, "failed")]


def test_worker_marks_indexed_when_text_and_vector_succeed() -> None:
    doc = _document()
    group_id = uuid4()
    repo = _FakeDocumentRepository(doc, [group_id])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant)

    worker.process_document(doc.id, pre_extracted_text="document body")

    assert len(es.calls) == 1
    assert len(qdrant.calls) == 1
    qdrant_chunks = qdrant.calls[0]
    assert qdrant_chunks
    assert qdrant_chunks[0]["group_id"] == [str(group_id)]
    assert repo.indexed_updates == [(doc.id, "indexed", None)]
    assert repo.status_updates == []


def test_worker_indexes_filename_path_and_content_fields() -> None:
    doc = _document()
    doc.path = "/data/ingest/test1.pdf"
    group_id = uuid4()
    repo = _FakeDocumentRepository(doc, [group_id])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant)

    worker.process_document(doc.id, pre_extracted_text="Original extracted text")

    assert len(es.calls) == 1
    indexed_body = es.calls[0][1]
    assert indexed_body["path"] == "/data/ingest/test1.pdf"
    assert indexed_body["filename"] == "test1.pdf"
    assert indexed_body["content_original"] == "Original extracted text"
    assert indexed_body["content_english"] == "Original extracted text"
    assert indexed_body["title"] == "Test document"


def test_worker_indexes_filename_fallback_when_path_is_none() -> None:
    doc = _document()
    doc.path = None
    doc.title = "My Document Title"
    repo = _FakeDocumentRepository(doc, [uuid4()])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant)

    worker.process_document(doc.id, pre_extracted_text="Some content")

    indexed_body = es.calls[0][1]
    assert indexed_body["filename"] == "My Document Title"
    assert indexed_body["path"] == ""


def test_process_document_returns_process_result_on_success() -> None:
    doc = _document()
    repo = _FakeDocumentRepository(doc, [uuid4()])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    translator = _FakeTranslator(translated="translated body")
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant, translator=translator)

    result = worker.process_document(doc.id, pre_extracted_text="raw body")

    assert isinstance(result, ProcessResult)
    assert result.extracted_text == "raw body"
    assert result.translated_text == "translated body"


def test_process_document_raises_on_failure() -> None:
    doc = _document()
    repo = _FakeDocumentRepository(doc, [uuid4()])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch(fail=True)
    qdrant = _FakeQdrant()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant)

    with pytest.raises(RuntimeError, match="elasticsearch_unavailable"):
        worker.process_document(doc.id, pre_extracted_text="raw body")

    assert repo.status_updates == [(doc.id, "failed")]
