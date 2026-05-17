"""Synchronous document ingestion pipeline."""

from __future__ import annotations

import hashlib
import logging
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, NamedTuple
from uuid import UUID

from services.alerts.service import AlertMatcher
from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository
from services.extraction.base import AttachmentData
from services.extraction.registry import ExtractorRegistry
from services.intelligence.worker import IntelligenceWorker
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import TextEncoder
from services.search.meili_provider import MeilisearchSearchProvider
from services.search.meili_types import ChunkMetadata, SearchChunkRecord
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.correlation import get_correlation_id
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)


class ProcessResult(NamedTuple):
    """Result returned by process_document on success."""

    extracted_text: str
    translated_text: str


class PipelineWorker:
    """Orchestrate extraction, translation, chunking, embedding, and indexing."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        extractor_registry: ExtractorRegistry,
        translator: LibreTranslateClient,
        encoder: TextEncoder,
        es_client: ElasticsearchSearchClient,
        qdrant_client: QdrantSearchClient,
        meili_provider: MeilisearchSearchProvider | None = None,
        intelligence_worker: IntelligenceWorker | None = None,
        alert_matcher: AlertMatcher | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._doc_repo = document_repository
        self._extractor = extractor_registry
        self._translator = translator
        self._encoder = encoder
        self._es = es_client
        self._qdrant = qdrant_client
        self._meili = meili_provider
        self._intelligence = intelligence_worker
        self._alert_matcher = alert_matcher
        self._metrics = metrics

    def process_document(
        self, document_id: UUID, pre_extracted_text: str | None = None
    ) -> ProcessResult | None:
        """Run the full pipeline for a single document.

        When *pre_extracted_text* is supplied it is used directly, bypassing
        the file extractor. This is required for connectors that fetch content
        over a network API rather than from a local file path.

        On success returns a :class:`ProcessResult` with both the raw extracted
        text and the translated text so the caller can persist them. On any
        unhandled exception the document status is set to ``"failed"`` and the
        exception is re-raised.
        """
        try:
            result = self._run(document_id, pre_extracted_text=pre_extracted_text)
            if self._metrics is not None:
                self._metrics.pipeline_documents_total.labels("document", "success").inc()
            return result
        except Exception:
            if self._metrics is not None:
                self._metrics.pipeline_documents_total.labels("document", "failure").inc()
            logger.exception(
                "Pipeline failed for document_id=%s correlation=%s",
                document_id,
                get_correlation_id(),
            )
            self._doc_repo.update_status(document_id, "failed")
            raise

    def _run(
        self,
        document_id: UUID,
        pre_extracted_text: str | None = None,
        _seen: frozenset[str] | None = None,
    ) -> ProcessResult:
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        allowed_group_ids = [
            str(group_id) for group_id in self._doc_repo.source_group_ids(doc.source_id)
        ]

        # 1. Extract — use pre-extracted text when available (API sources),
        #    otherwise read from the local file path (folder sources).
        start = time.perf_counter()
        if pre_extracted_text is not None:
            text = pre_extracted_text
        elif doc.path is not None:
            text = self._extractor.extract(Path(doc.path), doc.mime_type)
        else:
            raise ValueError(
                f"Document {document_id} has neither a file path nor pre_extracted_text"
            )
        if self._metrics is not None:
            self._metrics.pipeline_stage_duration_seconds.labels("extraction").observe(
                time.perf_counter() - start
            )
            self._metrics.pipeline_documents_total.labels("extraction", "success").inc()
            if doc.path is not None:
                with suppress(OSError):
                    self._metrics.pipeline_document_bytes.labels(doc.source).observe(
                        float(Path(doc.path).stat().st_size)
                    )

        # 2. Translate (falls back to original text on failure)
        start = time.perf_counter()
        translated = self._translator.translate(text, source_lang=doc.source_language)
        translation_quality: str | None = "fast" if translated != text else None
        if self._metrics is not None:
            self._metrics.translation_duration_seconds.labels("pipeline").observe(
                time.perf_counter() - start
            )
            self._metrics.translation_requests_total.labels("pipeline", "success").inc()
            self._metrics.translation_characters_total.labels("pipeline").inc(len(text))

        # 3. Chunk
        start = time.perf_counter()
        chunks = chunk_text(translated)
        if self._metrics is not None:
            self._metrics.pipeline_stage_duration_seconds.labels("chunking").observe(
                time.perf_counter() - start
            )
            self._metrics.pipeline_chunks_total.labels("success").inc(len(chunks))

        # 4. Index full document in Elasticsearch. This is intentionally before
        #    vector embedding so an Ollama/Qdrant outage does not prevent BM25
        #    text search from receiving the document.
        start = time.perf_counter()
        self._es.index_document(
            str(document_id),
            {
                "document_id": str(document_id),
                "path": doc.path or "",
                "filename": Path(doc.path).name if doc.path else doc.title or "",
                "content_original": text,
                "content_english": translated,
                "title": doc.title or "",
                "summary": "",
                "tags": [],
                "metadata": doc.metadata,
                "allowed_group_ids": allowed_group_ids,
            },
        )

        if self._metrics is not None:
            self._metrics.search_backend_duration_seconds.labels("elasticsearch", "index").observe(
                time.perf_counter() - start
            )
            self._metrics.search_index_documents.labels("elasticsearch").inc()

        # 5. Index chunks in Meilisearch when configured. This mirrors the
        #    backfill record shape so live ingestion and reindex agree.
        if self._meili is not None:
            try:
                meili_records = [
                    SearchChunkRecord.from_parts(
                        document_id=str(document_id),
                        chunk_index=idx,
                        title=doc.title or "",
                        content=chunk_text_content,
                        allowed_group_ids=allowed_group_ids,
                        metadata=ChunkMetadata(
                            source=doc.source,
                            mime_type=doc.mime_type,
                            file_name=Path(doc.path).name if doc.path else None,
                            language=doc.source_language,
                        ),
                        content_en=translated,
                    )
                    for idx, chunk_text_content in enumerate(chunks)
                ]
                if meili_records:
                    start = time.perf_counter()
                    self._meili.index_batch(meili_records)
                    if self._metrics is not None:
                        self._metrics.search_backend_duration_seconds.labels(
                            "meilisearch", "index"
                        ).observe(time.perf_counter() - start)
                        self._metrics.search_index_documents.labels("meilisearch").inc()
            except Exception as exc:
                logger.error(
                    "Meilisearch indexing failed for document_id=%s error_type=%s correlation=%s",
                    document_id,
                    exc.__class__.__name__,
                    get_correlation_id(),
                )

        # 6. Index chunks in Qdrant. Vector indexing is degraded/best-effort
        #    relative to text indexing: failures are logged safely but do not
        #    turn a text-indexed document into a failed document.
        #    Both original and translated text are chunked and indexed so that
        #    vector search can match in either language.
        try:
            qdrant_chunks: list[dict[str, Any]] = []

            def _build_chunk(
                chunk_text_content: str,
                idx: int,
                *,
                lang: str | None,
                suffix: str,
            ) -> dict[str, Any]:
                vector = self._encoder.encode(chunk_text_content)
                entry: dict[str, Any] = {
                    "chunk_id": f"{document_id}-{suffix}-{idx}",
                    "document_id": str(document_id),
                    "group_id": allowed_group_ids,
                    "chunk_index": idx,
                    "text": chunk_text_content,
                    "vector": vector,
                    "source_id": str(doc.source_id),
                }
                if doc.title:
                    entry["title"] = doc.title
                if lang:
                    entry["language"] = lang
                return entry

            # Original language chunks
            for idx, chunk_text_content in enumerate(chunk_text(text)):
                qdrant_chunks.append(
                    _build_chunk(chunk_text_content, idx, lang=doc.source_language, suffix="orig")
                )

            # Translated chunks (when translation differs from original)
            for idx, chunk_text_content in enumerate(chunks):
                qdrant_chunks.append(
                    _build_chunk(chunk_text_content, idx, lang=doc.target_language, suffix="trans")
                )

            if qdrant_chunks:
                start = time.perf_counter()
                # delete_existing removes stale chunks from prior runs before writing new ones.
                self._qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)
                if self._metrics is not None:
                    self._metrics.search_backend_duration_seconds.labels(
                        "qdrant", "upsert"
                    ).observe(time.perf_counter() - start)
                    self._metrics.search_index_documents.labels("qdrant").inc()
        except Exception as exc:
            logger.error(
                "Vector indexing failed for document_id=%s error_type=%s correlation=%s",
                document_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

        # 7. Update status after text indexing has succeeded. Vector/Meilisearch
        #    indexing may be degraded; a future async job model should persist
        #    stage-specific retry state for those failures.
        self._doc_repo.update_indexed(document_id, "indexed", translation_quality)

        # 8. Intelligence (best-effort, never blocking)
        if self._intelligence is not None and translation_quality in ("fast", "high"):
            try:
                self._intelligence.process_document(doc.id, translated)
            except Exception:
                logger.exception(
                    "Intelligence failed for document_id=%s correlation=%s",
                    document_id,
                    get_correlation_id(),
                )

        # 9. Alert matching (best-effort, never blocking)
        if self._alert_matcher is not None:
            try:
                self._alert_matcher.match_document(doc, translated)
            except Exception:
                logger.exception(
                    "Alert matching failed for document_id=%s correlation=%s",
                    document_id,
                    get_correlation_id(),
                )

        # 10. Process email/archive attachments as child documents (best-effort).
        #     _seen tracks SHA-256 hashes of content already processed in this
        #     call chain to break circular references (e.g. ZIP-A → ZIP-B → ZIP-A).
        if doc.path is not None:
            extractor = self._extractor.get(doc.mime_type)
            if extractor is not None and hasattr(extractor, "extract_attachments"):
                try:
                    attachments: list[AttachmentData] = extractor.extract_attachments(
                        Path(doc.path)
                    )
                    self._process_attachments(document_id, doc, attachments, _seen or frozenset())
                except Exception:
                    logger.exception(
                        "Attachment extraction failed for document_id=%s correlation=%s",
                        document_id,
                        get_correlation_id(),
                    )

        return ProcessResult(extracted_text=text, translated_text=translated)

    def _process_attachments(
        self,
        parent_id: UUID,
        parent_doc: Any,
        attachments: list[AttachmentData],
        _seen: frozenset[str],
    ) -> None:
        """Create a child document and run the pipeline for each attachment."""
        for att in attachments:
            sha256 = hashlib.sha256(att.data).hexdigest()
            if sha256 in _seen:
                logger.debug(
                    "Skipping duplicate attachment filename=%s parent_id=%s sha256=%s",
                    att.filename,
                    parent_id,
                    sha256,
                )
                continue

            # Skip attachment types we cannot extract text from
            if self._extractor.get(att.mime_type) is None:
                logger.debug(
                    "Skipping attachment with unsupported mime_type=%s filename=%s parent_id=%s",
                    att.mime_type,
                    att.filename,
                    parent_id,
                )
                continue
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=Path(att.filename).suffix or ".bin", delete=False
                ) as tmp:
                    tmp.write(att.data)
                    tmp_path = tmp.name

                child_external_id = (
                    f"{parent_doc.external_id}::attachment::{att.filename}::{sha256[:12]}"
                )
                child_doc = self._doc_repo.create(
                    source_id=parent_doc.source_id,
                    external_id=child_external_id,
                    source=parent_doc.source,
                    mime_type=att.mime_type,
                    path=tmp_path,
                    title=att.filename,
                    source_language=parent_doc.source_language,
                    metadata={"parent_document_id": str(parent_id)},
                )
                if child_doc is None:
                    # Already ingested — dedup hit
                    Path(tmp_path).unlink(missing_ok=True)
                    continue

                try:
                    self._run(child_doc.id, _seen=_seen | {sha256})
                    logger.info(
                        "Attachment processed: parent_id=%s child_id=%s filename=%s",
                        parent_id,
                        child_doc.id,
                        att.filename,
                    )
                except Exception:
                    logger.exception(
                        "Attachment pipeline failed: parent_id=%s filename=%s child_id=%s",
                        parent_id,
                        att.filename,
                        child_doc.id,
                    )
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                logger.exception(
                    "Failed to create child document for attachment: parent_id=%s filename=%s",
                    parent_id,
                    att.filename,
                )
