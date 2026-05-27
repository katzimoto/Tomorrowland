"""Slow worker for high-quality translation enrichment."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from services.alerts.service import AlertMatcher
from services.chunking.splitter import chunk_text
from services.documents.repository import (
    DocumentRepository,
    TranslationVersionRepository,
)
from services.extraction.registry import ExtractorRegistry
from services.intelligence.worker import IntelligenceWorker
from services.pipeline.jobs import PipelineJobRepository
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import TextEncoder
from services.search.meili_provider import MeilisearchSearchProvider
from services.search.meili_types import ChunkMetadata, SearchChunkRecord
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.correlation import get_correlation_id
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

_ALLOWED_JOB_TYPES = ["enrich_document"]


class SlowWorker:
    """Re-translate, re-chunk, and re-index documents with pending_high quality."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        extractor_registry: ExtractorRegistry | None,
        translator: LibreTranslateClient,
        encoder: TextEncoder,
        es_client: ElasticsearchSearchClient,
        qdrant_client: QdrantSearchClient,
        version_repository: TranslationVersionRepository | None = None,
        meili_provider: MeilisearchSearchProvider | None = None,
        intelligence_worker: IntelligenceWorker | None = None,
        alert_matcher: AlertMatcher | None = None,
    ) -> None:
        self._doc_repo = document_repository
        self._extractor = extractor_registry or ExtractorRegistry()
        self._translator = translator
        self._encoder = encoder
        self._es = es_client
        self._qdrant = qdrant_client
        self._meili = meili_provider
        self._intelligence = intelligence_worker
        self._version_repo = version_repository
        self._alert_matcher = alert_matcher

    def process_document(self, document_id: UUID) -> None:
        """Run the enrichment pipeline for a single document.

        On success the document translation_quality is set to ``"high"`` and
        status to ``"indexed"``. On any unhandled exception the version status
        is set to ``"failed"`` and the error is logged (enrichment is
        best-effort).
        """
        try:
            self._run(document_id)
        except Exception:
            logger.exception(
                "Slow worker failed for document_id=%s correlation=%s",
                document_id,
                get_correlation_id(),
            )
            # Best-effort: mark the document status as failed only if no
            # version repository is wired (backward compat). When versioned,
            # only the version is marked failed.
            if self._version_repo is None:
                self._doc_repo.update_status(document_id, "failed")

    def _run(self, document_id: UUID) -> None:
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        if doc.path is None:
            raise ValueError(f"Document {document_id} has no path")

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
            text = self._extractor.extract(Path(doc.path), doc.mime_type).text

            # 2. Translate
            translated = self._translator.translate(text, source_lang=doc.source_language)

            # 3. No-op guard: translation returned the same text (document already
            #    in the target language, or LibreTranslate failed auto-detect).
            #    Mark failed so the tab doesn't appear and quality stays unchanged.
            _is_no_op = bool(text) and translated == text
            if _is_no_op or not translated:
                reason = (
                    "Document already in target language or LibreTranslate returned unchanged text"
                    if _is_no_op
                    else "LibreTranslate returned empty translation"
                )
                logger.info(
                    "Slow worker no-op for document_id=%s version_id=%s: %s",
                    doc.id,
                    version_id,
                    reason,
                )
                self._version_repo.update_version_status(
                    version_id, "failed", error_summary=reason
                )
                return

            # 4. Store translated text on version
            self._version_repo.update_version_status(
                version_id, "available", translated_text=translated
            )

            # 5. Chunk and index (reuse legacy indexing)
            self._index_document(doc, translated, original=text)

            # 6. Update document summary quality
            self._doc_repo.update_translation_quality(doc.id, "high")

        except Exception:
            self._version_repo.update_version_status(
                version_id, "failed", error_summary="Translation failed"
            )
            raise

    def _run_legacy(self, doc: Any) -> None:
        """Legacy non-versioned enrichment path."""
        # 1. Extract
        text = self._extractor.extract(Path(doc.path), doc.mime_type).text

        # 2. Translate
        translated = self._translator.translate(text, source_lang=doc.source_language)

        # 3. Chunk and index
        self._index_document(doc, translated, original=text)

        # 4. Update quality and status
        self._doc_repo.update_indexed(doc.id, "indexed", "high")

    def _index_document(self, doc: Any, translated: str, original: str = "") -> None:
        """Chunk, embed, and index a document (both original and translated)."""
        document_id = doc.id
        allowed_group_ids = [
            str(group_id) for group_id in self._doc_repo.source_group_ids(doc.source_id)
        ]

        # Chunk both original and translated text separately so Meilisearch records
        # pair original chunk text (content) with its translated chunk (content_en).
        original_chunks = (
            list(chunk_text(original, language=doc.source_language)) if original else []
        )
        translated_chunks = list(chunk_text(translated, language=doc.target_language))

        # Index full document in Elasticsearch (preserve original text on re-index)
        self._es.index_document(
            str(document_id),
            {
                "document_id": str(document_id),
                "path": doc.path or "",
                "filename": Path(doc.path).name if doc.path else doc.title or "",
                "content_original": original or translated,
                "content_english": translated,
                "title": doc.title or "",
                "summary": "",
                "tags": [],
                "metadata": doc.metadata,
                "allowed_group_ids": allowed_group_ids,
            },
        )

        # Index chunks in Meilisearch when configured
        if self._meili is not None:
            try:
                pair_count = min(len(original_chunks), len(translated_chunks))
                meili_records = [
                    SearchChunkRecord.from_parts(
                        document_id=str(document_id),
                        chunk_index=idx,
                        title=doc.title or "",
                        content=orig_chunk,
                        allowed_group_ids=allowed_group_ids,
                        metadata=ChunkMetadata(
                            source=doc.source,
                            mime_type=doc.mime_type,
                            file_name=Path(doc.path).name if doc.path else None,
                            language=doc.source_language,
                        ),
                        content_en=tran_chunk if translated != original else None,
                    )
                    for idx, (orig_chunk, tran_chunk) in enumerate(
                        zip(
                            original_chunks[:pair_count],
                            translated_chunks[:pair_count],
                            strict=False,
                        )
                    )
                ]
                for idx in range(pair_count, len(original_chunks)):
                    meili_records.append(
                        SearchChunkRecord.from_parts(
                            document_id=str(document_id),
                            chunk_index=idx,
                            title=doc.title or "",
                            content=original_chunks[idx],
                            allowed_group_ids=allowed_group_ids,
                            metadata=ChunkMetadata(
                                source=doc.source,
                                mime_type=doc.mime_type,
                                file_name=Path(doc.path).name if doc.path else None,
                                language=doc.source_language,
                            ),
                            content_en=None,
                        )
                    )
                if meili_records:
                    self._meili.index_batch(meili_records)
            except Exception as exc:
                logger.error(
                    "Meilisearch indexing failed during enrichment for "
                    "document_id=%s error_type=%s correlation=%s",
                    document_id,
                    exc.__class__.__name__,
                    get_correlation_id(),
                )

        # Build Qdrant points for both original and translated chunks
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

            for idx, chunk_text_content in enumerate(original_chunks):
                qdrant_chunks.append(
                    _build_chunk(chunk_text_content, idx, lang=doc.source_language, suffix="orig")
                )

            for idx, chunk_text_content in enumerate(translated_chunks):
                qdrant_chunks.append(
                    _build_chunk(chunk_text_content, idx, lang=doc.target_language, suffix="trans")
                )

            if qdrant_chunks:
                self._qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)
        except Exception as exc:
            logger.error(
                "Vector indexing failed during enrichment for "
                "document_id=%s error_type=%s correlation=%s",
                document_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

        # Alert matching (best-effort, never blocking)
        if self._alert_matcher is not None:
            try:
                self._alert_matcher.match_document(doc, translated)
            except Exception:
                logger.exception(
                    "Alert matching failed during enrichment for document_id=%s correlation=%s",
                    document_id,
                    get_correlation_id(),
                )

        # Intelligence (best-effort, never blocking)
        if self._intelligence is not None:
            try:
                self._intelligence.process_document(doc.id, translated)
            except Exception:
                logger.exception(
                    "Intelligence failed during enrichment for document_id=%s correlation=%s",
                    document_id,
                    get_correlation_id(),
                )


def run_enrich_once(
    job_repo: PipelineJobRepository,
    worker: SlowWorker,
    worker_id: str = "enrich-worker",
    metrics: MetricsRegistry | None = None,
) -> bool:
    """Claim one ``enrich_document`` job and process it.

    Args:
        job_repo: Queue repository for claiming and updating jobs.
        worker: SlowWorker instance for document enrichment.
        worker_id: Identifier stamped on claimed jobs (for stale-lock tracking).
        metrics: Optional metrics registry; pass ``None`` to disable instrumentation.

    Returns:
        ``True`` if a job was claimed and processed, ``False`` if none available.
    """
    claimed = job_repo.claim_next(worker_id, job_types=_ALLOWED_JOB_TYPES)
    if claimed is None:
        return False

    job_id: UUID = claimed["id"]
    document_id: UUID = claimed["document_id"]
    job_type: str = claimed["job_type"]
    attempts: int = claimed["attempts"]
    max_attempts: int = claimed["max_attempts"]

    if metrics is not None:
        metrics.pipeline_jobs_claimed_total.labels(worker_type="enrich", job_type=job_type).inc()

    job_repo.mark_running_stage(job_id, "enrich")

    start = time.monotonic()
    try:
        worker.process_document(document_id)
    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="enrich")
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type="enrich", job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type="enrich",
                    job_type=job_type,
                    stage="enrich",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "enrich job retried: worker_id=%s job_type=%s job_id=%s "
                "attempt=%d max_attempts=%d error_type=%s",
                worker_id,
                job_type,
                job_id,
                attempts,
                max_attempts,
                error_type,
            )
        else:
            job_repo.mark_dead_letter(job_id, exc)
            if metrics is not None:
                metrics.pipeline_jobs_dead_lettered_total.labels(
                    worker_type="enrich", job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type="enrich",
                    job_type=job_type,
                    stage="enrich",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "enrich job dead-lettered: worker_id=%s job_type=%s job_id=%s "
                "attempts=%d error_type=%s",
                worker_id,
                job_type,
                job_id,
                attempts,
                error_type,
            )
        return True

    elapsed = time.monotonic() - start
    job_repo.mark_succeeded(job_id)
    if metrics is not None:
        metrics.pipeline_jobs_succeeded_total.labels(worker_type="enrich", job_type=job_type).inc()
        metrics.pipeline_job_duration_seconds.labels(
            worker_type="enrich",
            job_type=job_type,
            stage="enrich",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "enrich job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )

    return True


def run_enrich_loop(
    job_repo: PipelineJobRepository,
    worker: SlowWorker,
    worker_id: str = "enrich-worker",
    poll_interval: float = 1.0,
    metrics: MetricsRegistry | None = None,
) -> None:
    """Run ``run_enrich_once`` in a loop until interrupted."""
    logger.info(
        "enrich worker started: worker_id=%s poll_interval=%.1f",
        worker_id,
        poll_interval,
    )
    try:
        while True:
            if metrics is not None:
                metrics.worker_heartbeat_timestamp_seconds.labels(
                    worker_type="enrich", worker_id=worker_id
                ).set_to_current_time()

            try:
                ran = run_enrich_once(job_repo, worker, worker_id=worker_id, metrics=metrics)
            except Exception as exc:
                logger.exception(
                    "unhandled enrich loop error: worker_id=%s error_type=%s",
                    worker_id,
                    type(exc).__name__,
                )
                time.sleep(poll_interval)
                continue

            if not ran:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("enrich worker shutting down: worker_id=%s", worker_id)


if __name__ == "__main__":
    from sqlalchemy import create_engine

    from services.intelligence.ollama_client import OllamaClient
    from services.intelligence.repository import IntelligenceRepository
    from services.search.factory import build_encoder
    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url)

    with engine.begin() as conn:
        doc_repo = DocumentRepository(conn)
        version_repo = TranslationVersionRepository(conn)
        es_client = ElasticsearchSearchClient(hosts=[settings.elastic_url])
        qdrant_client = QdrantSearchClient(url=settings.qdrant_url)
        translator = LibreTranslateClient(base_url=settings.libretranslate_url)
        encoder = build_encoder(settings)

        ollama_client = OllamaClient(
            base_url=settings.ollama_url,
            model=settings.ollama_model,
        )
        intelligence_worker = IntelligenceWorker(
            repository=IntelligenceRepository(conn),
            ollama_client=ollama_client,
            es_client=es_client,
            utility_model=settings.effective_utility_model,
        )

        worker = SlowWorker(
            document_repository=doc_repo,
            extractor_registry=ExtractorRegistry(
                enable_ocr=settings.enable_ocr,
                enable_legacy_office=settings.enable_legacy_office,
            ),
            translator=translator,
            encoder=encoder,
            es_client=es_client,
            qdrant_client=qdrant_client,
            version_repository=version_repo,
            intelligence_worker=intelligence_worker,
        )

        run_enrich_loop(
            PipelineJobRepository(conn),
            worker,
            worker_id="enrich-worker",
        )
