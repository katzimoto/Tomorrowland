"""Synchronous document ingestion pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import MockEncoder
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.correlation import get_correlation_id

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
    ) -> None:
        self._doc_repo = document_repository
        self._extractor = extractor_registry
        self._translator = translator
        self._encoder = encoder
        self._es = es_client
        self._qdrant = qdrant_client

    def process_document(self, doc_id: UUID) -> None:
        """Run the full pipeline for a single document.

        On success the document status is set to ``"indexed"``. On any
        unhandled exception the status is set to ``"failed"`` and the
        exception is re-raised after logging.
        """
        try:
            self._run(doc_id)
        except Exception:
            logger.exception(
                "Pipeline failed for doc_id=%s correlation=%s",
                doc_id,
                get_correlation_id(),
            )
            self._doc_repo.update_status(doc_id, "failed")
            raise

    def _run(self, doc_id: UUID) -> None:
        doc = self._doc_repo.get_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")
        if doc.path is None:
            raise ValueError(f"Document {doc_id} has no path")

        # 1. Extract
        text = self._extractor.extract(Path(doc.path), doc.mime_type)

        # 2. Translate (falls back to original text on failure)
        translated = self._translator.translate(text, source_lang=doc.source_language)
        translation_quality: str | None = "fast" if translated != text else None

        # 3. Chunk
        chunks = chunk_text(translated)

        # 4. Encode + build Qdrant points
        qdrant_chunks: list[dict[str, Any]] = []
        for idx, chunk_text_content in enumerate(chunks):
            vector = self._encoder.encode(chunk_text_content)
            qdrant_chunks.append(
                {
                    "chunk_id": f"{doc_id}-{idx}",
                    "doc_id": str(doc_id),
                    "group_id": "default",
                    "chunk_index": idx,
                    "text": chunk_text_content,
                    "vector": vector,
                }
            )

        # 5. Index full document in Elasticsearch
        self._es.index_document(
            str(doc_id),
            {
                "doc_id": str(doc_id),
                "content_english": translated,
                "title": doc.title or "",
                "summary": "",
                "tags": [],
                "metadata": doc.metadata,
                "allowed_group_ids": ["default"],
            },
        )

        # 6. Index chunks in Qdrant
        if qdrant_chunks:
            self._qdrant.upsert_chunks(qdrant_chunks)

        # 7. Update status
        self._doc_repo.update_indexed(doc_id, "indexed", translation_quality)
