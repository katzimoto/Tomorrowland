"""Slow worker for high-quality translation enrichment."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository, TranslationVersionRepository
from services.extraction.registry import ExtractorRegistry
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import MockEncoder
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.correlation import get_correlation_id

logger = logging.getLogger(__name__)


class SlowWorker:
    """Re-translate, re-chunk, and re-index documents with pending_high quality."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        extractor_registry: ExtractorRegistry | None,
        translator: LibreTranslateClient,
        encoder: MockEncoder,
        es_client: ElasticsearchSearchClient,
        qdrant_client: QdrantSearchClient,
        version_repository: TranslationVersionRepository | None = None,
    ) -> None:
        self._doc_repo = document_repository
        self._extractor = extractor_registry or ExtractorRegistry()
        self._translator = translator
        self._encoder = encoder
        self._es = es_client
        self._qdrant = qdrant_client
        self._version_repo = version_repository

    def process_document(self, doc_id: UUID) -> None:
        """Run the enrichment pipeline for a single document.

        On success the document translation_quality is set to ``"high"`` and
        status to ``"indexed"``. On any unhandled exception the version status
        is set to ``"failed"`` and the error is logged (enrichment is
        best-effort).
        """
        try:
            self._run(doc_id)
        except Exception:
            logger.exception(
                "Slow worker failed for doc_id=%s correlation=%s",
                doc_id,
                get_correlation_id(),
            )
            # Best-effort: mark the document status as failed only if no
            # version repository is wired (backward compat). When versioned,
            # only the version is marked failed.
            if self._version_repo is None:
                self._doc_repo.update_status(doc_id, "failed")

    def _run(self, doc_id: UUID) -> None:
        doc = self._doc_repo.get_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")
        if doc.path is None:
            raise ValueError(f"Document {doc_id} has no path")

        # If version repository is available, process pending versions
        if self._version_repo is not None:
            self._run_versioned(doc)
            return

        # Legacy path: process document directly
        self._run_legacy(doc)

    def _run_versioned(self, doc: Any) -> None:
        """Process the oldest pending version for a document."""
        assert self._version_repo is not None
        pending = self._version_repo.get_pending_versions(doc.id)
        if not pending:
            # Fallback to legacy behavior if no pending versions exist
            self._run_legacy(doc)
            return

        version = pending[0]
        version_id = UUID(str(version["id"]))

        try:
            self._version_repo.update_version_status(version_id, "running")

            # 1. Extract
            text = self._extractor.extract(Path(doc.path), doc.mime_type)

            # 2. Translate
            translated = self._translator.translate(text, source_lang=doc.source_language)

            # 3. Store translated text on version
            self._version_repo.update_version_status(
                version_id, "available", translated_text=translated
            )

            # 4. Chunk and index (reuse legacy indexing)
            self._index_document(doc, translated)

            # 5. Update document summary quality
            self._doc_repo.update_translation_quality(doc.id, "high")

        except Exception:
            self._version_repo.update_version_status(
                version_id, "failed", error_summary="Translation failed"
            )
            raise

    def _run_legacy(self, doc: Any) -> None:
        """Legacy non-versioned enrichment path."""
        # 1. Extract
        text = self._extractor.extract(Path(doc.path), doc.mime_type)

        # 2. Translate
        translated = self._translator.translate(text, source_lang=doc.source_language)

        # 3. Chunk and index
        self._index_document(doc, translated)

        # 4. Update quality and status
        self._doc_repo.update_indexed(doc.id, "indexed", "high")

    def _index_document(self, doc: Any, translated: str) -> None:
        """Chunk, embed, and index a translated document."""
        doc_id = doc.id
        chunks = chunk_text(translated)

        # Encode + build Qdrant points
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

        # Index full document in Elasticsearch
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

        # Index chunks in Qdrant
        if qdrant_chunks:
            self._qdrant.upsert_chunks(qdrant_chunks)
