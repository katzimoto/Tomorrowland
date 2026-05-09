"""Synchronous document ingestion pipeline."""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import UUID

from services.alerts.service import AlertMatcher
from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.intelligence.worker import IntelligenceWorker
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import MockEncoder
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.correlation import get_correlation_id
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)


class PipelineWorker:
    """Orchestrate extraction, translation, chunking, embedding, and indexing."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        extractor_registry: ExtractorRegistry,
        translator: LibreTranslateClient,
        encoder: MockEncoder,
        es_client: ElasticsearchSearchClient,
        qdrant_client: QdrantSearchClient,
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
        self._intelligence = intelligence_worker
        self._alert_matcher = alert_matcher
        self._metrics = metrics

    def process_document(self, doc_id: UUID, pre_extracted_text: str | None = None) -> None:
        """Run the full pipeline for a single document.

        When *pre_extracted_text* is supplied it is used directly, bypassing
        the file extractor. This is required for connectors that fetch content
        over a network API rather than from a local file path.

        On success the document status is set to ``"indexed"``. On any
        unhandled exception the status is set to ``"failed"`` and the
        exception is re-raised after logging.
        """
        try:
            self._run(doc_id, pre_extracted_text=pre_extracted_text)
            if self._metrics is not None:
                self._metrics.pipeline_documents_total.labels("document", "success").inc()
        except Exception:
            if self._metrics is not None:
                self._metrics.pipeline_documents_total.labels("document", "failure").inc()
            logger.exception(
                "Pipeline failed for doc_id=%s correlation=%s",
                doc_id,
                get_correlation_id(),
            )
            self._doc_repo.update_status(doc_id, "failed")
            raise

    def _run(self, doc_id: UUID, pre_extracted_text: str | None = None) -> None:
        doc = self._doc_repo.get_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        # 1. Extract — use pre-extracted text when available (API sources),
        #    otherwise read from the local file path (folder sources).
        start = time.perf_counter()
        if pre_extracted_text is not None:
            text = pre_extracted_text
        elif doc.path is not None:
            text = self._extractor.extract(Path(doc.path), doc.mime_type)
        else:
            raise ValueError(f"Document {doc_id} has neither a file path nor pre_extracted_text")
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
        allowed_group_ids = [
            str(group_id) for group_id in self._doc_repo.source_group_ids(doc.source_id)
        ]

        # 4. Encode + build Qdrant points
        qdrant_chunks: list[dict[str, Any]] = []
        for idx, chunk_text_content in enumerate(chunks):
            vector = self._encoder.encode(chunk_text_content)
            qdrant_chunks.append(
                {
                    "chunk_id": f"{doc_id}-{idx}",
                    "doc_id": str(doc_id),
                    "group_id": allowed_group_ids,
                    "chunk_index": idx,
                    "text": chunk_text_content,
                    "vector": vector,
                }
            )

        # 5. Index full document in Elasticsearch
        start = time.perf_counter()
        self._es.index_document(
            str(doc_id),
            {
                "doc_id": str(doc_id),
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

        # 6. Index chunks in Qdrant
        if qdrant_chunks:
            start = time.perf_counter()
            self._qdrant.upsert_chunks(qdrant_chunks)
            if self._metrics is not None:
                self._metrics.search_backend_duration_seconds.labels("qdrant", "upsert").observe(
                    time.perf_counter() - start
                )
                self._metrics.search_index_documents.labels("qdrant").inc()

        # 7. Update status
        self._doc_repo.update_indexed(doc_id, "indexed", translation_quality)

        # 8. Intelligence (best-effort, never blocking)
        if self._intelligence is not None and translation_quality in ("fast", "high"):
            try:
                self._intelligence.process_document(doc.id, translated)
            except Exception:
                logger.exception(
                    "Intelligence failed for doc_id=%s correlation=%s",
                    doc_id,
                    get_correlation_id(),
                )

        # 9. Alert matching (best-effort, never blocking)
        if self._alert_matcher is not None:
            try:
                self._alert_matcher.match_document(doc, translated)
            except Exception:
                logger.exception(
                    "Alert matching failed for doc_id=%s correlation=%s",
                    doc_id,
                    get_correlation_id(),
                )
