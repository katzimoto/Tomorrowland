from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from services.documents.models import DocumentRow
from services.pipeline.worker import PipelineWorker, ProcessResult
from services.search.meili_types import SearchChunkRecord


class _FakeDocumentRepository:
    def __init__(self, doc: DocumentRow, group_ids: list[UUID]) -> None:
        self._doc = doc
        self._group_ids = group_ids
        self.indexed_updates: list[tuple[UUID, str, str | None]] = []
        self.status_updates: list[tuple[UUID, str]] = []

    def get_by_id(self, document_id: UUID) -> DocumentRow | None:
        return self._doc if document_id == self._doc.id else None

    def source_group_ids(self, source_id: UUID) -> list[UUID]:
        assert source_id == self._doc.source_id
        return self._group_ids

    def update_indexed(
        self,
        document_id: UUID,
        status: str,
        translation_quality: str | None,
    ) -> None:
        self.indexed_updates.append((document_id, status, translation_quality))

    def update_status(self, document_id: UUID, status: str) -> None:
        self.status_updates.append((document_id, status))


class _FakeExtractor:
    def extract(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("pre_extracted_text should bypass extraction")

    def get(self, mime_type: str) -> object | None:
        return None


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

    def index_document(self, document_id: str, body: dict[str, object]) -> None:
        self.calls.append((document_id, body))
        if self.fail:
            raise RuntimeError("elasticsearch_unavailable")


class _FakeQdrant:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[dict[str, object]]] = []

    def upsert_chunks(self, chunks: list[dict[str, object]], delete_existing: bool = False) -> None:
        self.calls.append(chunks)
        if self.fail:
            raise RuntimeError("qdrant_unavailable")

    def delete_by_doc_id(self, document_id: str) -> None:
        pass


class _FakeMeili:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[SearchChunkRecord]] = []

    def index_batch(self, documents: list[SearchChunkRecord]) -> None:
        self.calls.append(documents)
        if self.fail:
            raise RuntimeError("meili_unavailable")


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
    meili: _FakeMeili | None = None,
    translator: _FakeTranslator | None = None,
) -> PipelineWorker:
    return PipelineWorker(
        document_repository=repo,  # type: ignore[arg-type]
        extractor_registry=_FakeExtractor(),  # type: ignore[arg-type]
        translator=translator or _FakeTranslator(),  # type: ignore[arg-type]
        encoder=encoder,  # type: ignore[arg-type]
        es_client=es,  # type: ignore[arg-type]
        qdrant_client=qdrant,  # type: ignore[arg-type]
        meili_provider=meili,  # type: ignore[arg-type]
    )


def test_worker_indexes_text_when_encoder_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
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


def test_worker_indexes_chunks_in_meilisearch_when_configured() -> None:
    doc = _document()
    doc.path = "/data/ingest/test1.pdf"
    group_id = uuid4()
    repo = _FakeDocumentRepository(doc, [group_id])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    meili = _FakeMeili()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant, meili=meili)

    worker.process_document(doc.id, pre_extracted_text="document body")

    assert len(meili.calls) == 1
    records = meili.calls[0]
    assert records
    first_record = records[0]
    assert first_record.document_id == str(doc.id)
    assert first_record.title == "Test document"
    assert first_record.content == "document body"
    assert first_record.content_en == "document body"
    assert first_record.allowed_group_ids == [str(group_id)]
    assert first_record.metadata.file_name == "test1.pdf"
    assert repo.indexed_updates == [(doc.id, "indexed", None)]


def test_meili_content_is_original_and_content_en_is_translation() -> None:
    """Meilisearch records use original text for content and translated for content_en."""
    doc = _document()
    doc.source_language = "zh"
    doc.target_language = "en"
    group_id = uuid4()
    repo = _FakeDocumentRepository(doc, [group_id])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    meili = _FakeMeili()
    translator = _FakeTranslator(translated="translated english text")
    worker = _worker(
        repo=repo, encoder=encoder, es=es, qdrant=qdrant, meili=meili, translator=translator
    )

    worker.process_document(doc.id, pre_extracted_text="原始中文文本")

    assert len(meili.calls) == 1
    records = meili.calls[0]
    assert records
    first = records[0]
    assert first.content == "原始中文文本"
    assert first.content_en == "translated english text"
    assert first.content != first.content_en


def test_meili_content_en_is_none_when_no_translation() -> None:
    """Meilisearch content_en should be None when text equals translation."""
    doc = _document()
    doc.source_language = "en"
    group_id = uuid4()
    repo = _FakeDocumentRepository(doc, [group_id])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    meili = _FakeMeili()
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant, meili=meili)

    worker.process_document(doc.id, pre_extracted_text="english text")

    assert len(meili.calls) == 1
    records = meili.calls[0]
    assert records
    first = records[0]
    assert first.content == "english text"
    assert first.content_en is None


def test_worker_marks_indexed_when_meilisearch_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    doc = _document()
    repo = _FakeDocumentRepository(doc, [uuid4()])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()
    meili = _FakeMeili(fail=True)
    worker = _worker(repo=repo, encoder=encoder, es=es, qdrant=qdrant, meili=meili)

    caplog.set_level(logging.ERROR, logger="services.pipeline.worker")

    worker.process_document(doc.id, pre_extracted_text="document body")

    assert len(meili.calls) == 1
    assert repo.indexed_updates == [(doc.id, "indexed", None)]
    assert repo.status_updates == []
    assert "Meilisearch indexing failed" in caplog.text


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


# ---------------------------------------------------------------------------
# Attachment processing tests
# ---------------------------------------------------------------------------


class _FakeAttachmentExtractor:
    """Fake extractor that supports both extract() and extract_attachments()."""

    def __init__(self, attachments: list[object]) -> None:
        self._attachments = attachments

    def extract(self, path: object) -> str:
        return "attachment text content"

    def extract_attachments(self, path: object) -> list[object]:
        return self._attachments


class _FakeExtractorRegistry:
    """Fake registry that routes MIME types to concrete fakes."""

    def __init__(
        self,
        *,
        email_extractor: object | None = None,
        attachment_extractor: object | None = None,
    ) -> None:
        self._email = email_extractor
        self._attachment = attachment_extractor

    def extract(self, path: object, mime_type: str) -> str:
        if self._email is not None and mime_type == "message/rfc822":
            return ""
        return "text content"

    def get(self, mime_type: str) -> object | None:
        if mime_type == "message/rfc822":
            return self._email
        if mime_type == "text/plain":
            return self._attachment
        return None


class _FakeDocumentRepositoryWithCreate(_FakeDocumentRepository):
    def __init__(self, doc: DocumentRow, group_ids: list[UUID]) -> None:
        super().__init__(doc, group_ids)
        self.created_children: list[dict[str, object]] = []
        self._child_doc: DocumentRow | None = None

    def set_child_doc(self, child: DocumentRow) -> None:
        self._child_doc = child

    def create(self, **kwargs: object) -> DocumentRow | None:
        self.created_children.append(dict(kwargs))
        return self._child_doc

    def get_by_id(self, document_id: UUID) -> DocumentRow | None:
        if self._child_doc is not None and document_id == self._child_doc.id:
            return self._child_doc
        return super().get_by_id(document_id)


def test_worker_skips_attachment_when_mime_not_supported(tmp_path: Path) -> None:
    from services.extraction.base import AttachmentData

    doc = _document()
    doc.mime_type = "message/rfc822"
    doc.path = str(tmp_path / "email.eml")
    (tmp_path / "email.eml").write_bytes(b"")

    att = AttachmentData(filename="image.png", mime_type="image/png", data=b"png_bytes")
    email_extractor = _FakeAttachmentExtractor([att])
    # image/png has no registered extractor → should be skipped
    registry = _FakeExtractorRegistry(email_extractor=email_extractor, attachment_extractor=None)

    repo = _FakeDocumentRepositoryWithCreate(doc, [uuid4()])
    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()

    worker = PipelineWorker(
        document_repository=repo,  # type: ignore[arg-type]
        extractor_registry=registry,  # type: ignore[arg-type]
        translator=_FakeTranslator(),  # type: ignore[arg-type]
        encoder=encoder,  # type: ignore[arg-type]
        es_client=es,  # type: ignore[arg-type]
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )

    worker.process_document(doc.id, pre_extracted_text="email body text")

    # No child documents created because image/png is not supported
    assert repo.created_children == []


def test_worker_creates_child_doc_for_supported_attachment(tmp_path: Path) -> None:
    from services.extraction.base import AttachmentData

    now = datetime.now(UTC)
    doc = _document()
    doc.mime_type = "message/rfc822"
    doc.path = str(tmp_path / "email.eml")
    (tmp_path / "email.eml").write_bytes(b"")

    att = AttachmentData(filename="report.txt", mime_type="text/plain", data=b"report content")
    email_extractor = _FakeAttachmentExtractor([att])
    # text/plain IS supported → child doc should be created
    registry = _FakeExtractorRegistry(
        email_extractor=email_extractor,
        attachment_extractor=_FakeAttachmentExtractor([]),  # no nested attachments
    )

    child_doc = DocumentRow(
        id=uuid4(),
        source_id=doc.source_id,
        external_id=f"{doc.external_id}::attachment::report.txt",
        source=doc.source,
        path=str(tmp_path / "child.txt"),
        mime_type="text/plain",
        title="report.txt",
        source_language=doc.source_language,
        target_language="en",
        status="pending",
        content_sha256="",
        metadata={"parent_document_id": str(doc.id)},
        created_at=now,
        updated_at=now,
    )
    (tmp_path / "child.txt").write_text("report content")

    repo = _FakeDocumentRepositoryWithCreate(doc, [uuid4()])
    repo.set_child_doc(child_doc)

    encoder = _FakeEncoder()
    es = _FakeElasticsearch()
    qdrant = _FakeQdrant()

    worker = PipelineWorker(
        document_repository=repo,  # type: ignore[arg-type]
        extractor_registry=registry,  # type: ignore[arg-type]
        translator=_FakeTranslator(),  # type: ignore[arg-type]
        encoder=encoder,  # type: ignore[arg-type]
        es_client=es,  # type: ignore[arg-type]
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )

    worker.process_document(doc.id, pre_extracted_text="email body text")

    assert len(repo.created_children) == 1
    created = repo.created_children[0]
    assert created["mime_type"] == "text/plain"
    assert created["title"] == "report.txt"
    assert "parent_document_id" in created["metadata"]  # type: ignore[operator]
    assert created["metadata"]["parent_document_id"] == str(doc.id)  # type: ignore[index]
    # Both parent and child should be indexed
    indexed_ids = {upd[0] for upd in repo.indexed_updates}
    assert doc.id in indexed_ids
    assert child_doc.id in indexed_ids
