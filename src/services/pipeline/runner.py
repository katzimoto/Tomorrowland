"""Durable pipeline job runner that claims jobs from the queue and processes them.

A single iteration performs:

1. Claim one ready ``pipeline_job`` via ``PipelineJobRepository.claim_next``.
2. Return early when no job is available.
3. Load the durable document payload from ``document_payloads``.
4. Call the existing ``PipelineWorker.process_document``.
5. Mark the job as succeeded, retry, or dead-letter based on outcome.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from services.documents.repository import DocumentRepository, TranslationVersionRepository
from services.extraction.registry import ExtractorRegistry
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.worker import PipelineWorker
from services.search.elastic import ElasticsearchSearchClient
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

_WORKER_TYPE = "pipeline"
_WORKER_ALLOWED_JOB_TYPES = ["process_document", "intelligence_document", "alert_document"]
_REAP_INTERVAL_SECONDS = 60.0


def run_once(
    job_repo: PipelineJobRepository,
    worker: PipelineWorker,
    worker_id: str = "worker-default",
    metrics: MetricsRegistry | None = None,
) -> bool:
    """Claim one job, process it, and mark it done.

    Args:
        job_repo: Queue repository for claiming and updating jobs.
        worker: Pipeline worker for document processing.
        worker_id: Identifier stamped on claimed jobs (for stale-lock tracking).
        metrics: Optional metrics registry; pass ``None`` to disable instrumentation.

    Returns:
        ``True`` if a job was claimed and processed, ``False`` if no job was available.
    """
    claimed = job_repo.claim_next(worker_id, job_types=_WORKER_ALLOWED_JOB_TYPES)
    if claimed is None:
        return False

    job_id: UUID = claimed["id"]
    document_id: UUID = claimed["document_id"]
    source_id: UUID = claimed["source_id"]
    job_type: str = claimed["job_type"]
    attempts: int = claimed["attempts"]
    max_attempts: int = claimed["max_attempts"]

    if metrics is not None:
        metrics.pipeline_jobs_claimed_total.labels(
            worker_type=_WORKER_TYPE, job_type=job_type
        ).inc()

    # Load durable payload
    payload: dict[str, Any] | None = job_repo.get_payload(document_id)
    pre_extracted_text: str | None = payload.get("content_text") if payload else None

    # ---- Dispatch by job type ----
    if job_type == "process_document":
        return _run_process_job(
            job_repo,
            worker,
            job_id,
            document_id,
            source_id,
            job_type,
            attempts,
            max_attempts,
            pre_extracted_text,
            worker_id,
            metrics,
            payload,
        )
    elif job_type == "intelligence_document":
        return _run_intelligence_job(
            job_repo,
            worker,
            job_id,
            document_id,
            job_type,
            attempts,
            max_attempts,
            payload,
            worker_id,
            metrics,
        )
    elif job_type == "alert_document":
        return _run_alert_job(
            job_repo,
            worker,
            job_id,
            document_id,
            job_type,
            attempts,
            max_attempts,
            payload,
            worker_id,
            metrics,
        )
    # Unknown job type — mark dead-letter immediately (should not happen with filtering)
    job_repo.mark_dead_letter(job_id, ValueError(f"unknown job_type: {job_type}"))
    return True


def _run_process_job(
    job_repo: PipelineJobRepository,
    worker: PipelineWorker,
    job_id: UUID,
    document_id: UUID,
    source_id: UUID,
    job_type: str,
    attempts: int,
    max_attempts: int,
    pre_extracted_text: str | None,
    worker_id: str,
    metrics: MetricsRegistry | None,
    payload: dict[str, Any] | None,
) -> bool:
    """Process a ``process_document`` job end-to-end."""
    job_repo.mark_running_stage(job_id, "process")

    start = time.monotonic()
    process_result = None
    try:
        process_result = worker.process_document(document_id, pre_extracted_text=pre_extracted_text)
    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="process")
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="process",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "pipeline job retried: worker_id=%s job_type=%s job_id=%s "
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
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="process",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "pipeline job dead-lettered: worker_id=%s job_type=%s job_id=%s "
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
        metrics.pipeline_jobs_succeeded_total.labels(
            worker_type=_WORKER_TYPE, job_type=job_type
        ).inc()
        metrics.pipeline_job_duration_seconds.labels(
            worker_type=_WORKER_TYPE,
            job_type=job_type,
            stage="process",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "pipeline job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )

    # Persist extracted and translated text so downstream workers operate from IDs only.
    if process_result is not None:
        try:
            job_repo.update_content_text(document_id, process_result.extracted_text)
        except Exception:
            logger.exception(
                "failed to persist extracted text: worker_id=%s error_type=PersistError",
                worker_id,
            )
        try:
            job_repo.update_translated_text(document_id, process_result.translated_text)
        except Exception:
            logger.exception(
                "failed to persist translated text: worker_id=%s error_type=PersistError",
                worker_id,
            )
        # Use extracted_text as fallback when the translator returned an empty
        # string (e.g. LibreTranslate returned {"translatedText": ""} for an
        # EML or other document whose content confused auto-detection).  Both
        # fields being empty means there is nothing worth storing.
        _version_text = process_result.translated_text or process_result.extracted_text
        if _version_text:
            try:
                doc = worker.document_repository.get_by_id(document_id)
                target_lang = doc.target_language if doc is not None else "en"
                version_repo = TranslationVersionRepository(job_repo._connection)
                existing = version_repo.find_pending_or_running(document_id, target_lang)
                if existing is None:
                    created = version_repo.create_version(
                        document_id=document_id,
                        label="Ingestion",
                        quality="fast",
                        request_type="ingestion",
                        target_language=target_lang,
                    )
                    version_id = UUID(str(created["id"]))
                else:
                    version_id = UUID(str(existing["id"]))
                version_repo.update_version_status(
                    version_id,
                    "available",
                    translated_text=_version_text,
                )
            except Exception:
                logger.exception(
                    "failed to create translation version: worker_id=%s error_type=PersistError",
                    worker_id,
                )

    # Enqueue downstream jobs after successful text processing
    # Vector job is always enqueued; intelligence and alert jobs are
    # best-effort and only enqueued when the worker has the dependency.
    try:
        job_repo.enqueue_document(
            document_id=document_id,
            source_id=source_id,
            job_type="vector_index_document",
        )
    except Exception:
        logger.exception(
            "failed to enqueue vector job: worker_id=%s error_type=EnqueueError",
            worker_id,
        )

    if worker.intelligence_worker is not None:
        try:
            job_repo.enqueue_document(
                document_id=document_id,
                source_id=source_id,
                job_type="intelligence_document",
            )
        except Exception:
            logger.exception(
                "failed to enqueue intelligence job: worker_id=%s error_type=EnqueueError",
                worker_id,
            )

    if worker.alert_matcher is not None:
        try:
            job_repo.enqueue_document(
                document_id=document_id,
                source_id=source_id,
                job_type="alert_document",
            )
        except Exception:
            logger.exception(
                "failed to enqueue alert job: worker_id=%s error_type=EnqueueError",
                worker_id,
            )

    return True


def _run_intelligence_job(
    job_repo: PipelineJobRepository,
    worker: PipelineWorker,
    job_id: UUID,
    document_id: UUID,
    job_type: str,
    attempts: int,
    max_attempts: int,
    payload: dict[str, Any] | None,
    worker_id: str,
    metrics: MetricsRegistry | None,
) -> bool:
    """Process an ``intelligence_document`` job (best-effort)."""
    intel = worker.intelligence_worker
    if intel is None or not hasattr(intel, "process_document"):
        job_repo.mark_succeeded(job_id)
        return True

    content = ""
    if payload is not None:
        content = payload.get("translated_text") or payload.get("content_text") or ""

    job_repo.mark_running_stage(job_id, "intelligence")

    start = time.monotonic()
    try:
        intel.process_document(document_id, content)
    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="intelligence")
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="intelligence",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "intelligence job retried: worker_id=%s job_type=%s job_id=%s "
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
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="intelligence",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "intelligence job dead-lettered: worker_id=%s job_type=%s job_id=%s "
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
        metrics.pipeline_jobs_succeeded_total.labels(
            worker_type=_WORKER_TYPE, job_type=job_type
        ).inc()
        metrics.pipeline_job_duration_seconds.labels(
            worker_type=_WORKER_TYPE,
            job_type=job_type,
            stage="intelligence",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "intelligence job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )
    return True


def _run_alert_job(
    job_repo: PipelineJobRepository,
    worker: PipelineWorker,
    job_id: UUID,
    document_id: UUID,
    job_type: str,
    attempts: int,
    max_attempts: int,
    payload: dict[str, Any] | None,
    worker_id: str,
    metrics: MetricsRegistry | None,
) -> bool:
    """Process an ``alert_document`` job (best-effort)."""
    matcher = worker.alert_matcher
    if matcher is None or not hasattr(matcher, "match_document"):
        job_repo.mark_succeeded(job_id)
        return True

    doc = worker.document_repository.get_by_id(document_id)
    if doc is None:
        job_repo.mark_succeeded(job_id)
        return True

    content = ""
    if payload is not None:
        content = payload.get("translated_text") or payload.get("content_text") or ""

    job_repo.mark_running_stage(job_id, "alert")

    start = time.monotonic()
    try:
        matcher.match_document(doc, content)
    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="alert")
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="alert",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "alert job retried: worker_id=%s job_type=%s job_id=%s "
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
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="alert",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "alert job dead-lettered: worker_id=%s job_type=%s job_id=%s "
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
        metrics.pipeline_jobs_succeeded_total.labels(
            worker_type=_WORKER_TYPE, job_type=job_type
        ).inc()
        metrics.pipeline_job_duration_seconds.labels(
            worker_type=_WORKER_TYPE,
            job_type=job_type,
            stage="alert",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "alert job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )
    return True


def run_loop(
    job_repo: PipelineJobRepository,
    worker: PipelineWorker,
    conn: Connection,
    worker_id: str = "worker-default",
    poll_interval: float = 1.0,
    metrics: MetricsRegistry | None = None,
) -> None:
    """Run ``run_once`` in a loop until interrupted.

    Emits a heartbeat gauge and queue-depth snapshot each iteration.
    Reaps stale locks every ``_REAP_INTERVAL_SECONDS`` seconds.
    Each iteration runs in its own short transaction so other
    processes (API, vector worker) see pipeline results immediately.
    """
    logger.info(
        "pipeline worker started: worker_id=%s poll_interval=%.1f",
        worker_id,
        poll_interval,
    )
    last_reap = time.monotonic()
    try:
        while True:
            now = time.monotonic()

            if metrics is not None:
                metrics.worker_heartbeat_timestamp_seconds.labels(
                    worker_type=_WORKER_TYPE, worker_id=worker_id
                ).set_to_current_time()
                counts = job_repo.count_by_status()
                for (status, jt), count in counts.items():
                    metrics.pipeline_queue_depth.labels(status=status, job_type=jt).set(count)

            if now - last_reap >= _REAP_INTERVAL_SECONDS:
                reaped = job_repo.reap_stale_locks()
                last_reap = now
                if reaped:
                    if metrics is not None:
                        metrics.pipeline_jobs_stale_lock_reaped_total.labels(
                            worker_type=_WORKER_TYPE
                        ).inc(reaped)
                    logger.info(
                        "stale pipeline locks reaped: worker_id=%s count=%d",
                        worker_id,
                        reaped,
                    )

            try:
                ran = run_once(job_repo, worker, worker_id=worker_id, metrics=metrics)
                if ran:
                    conn.commit()
                else:
                    conn.rollback()
            except Exception as exc:
                conn.rollback()
                error_type = type(exc).__name__
                if metrics is not None:
                    metrics.worker_loop_errors_total.labels(
                        worker_type=_WORKER_TYPE, error_type=error_type
                    ).inc()
                logger.exception(
                    "unhandled pipeline loop error: worker_id=%s error_type=%s",
                    worker_id,
                    error_type,
                )
                time.sleep(poll_interval)
                continue

            if not ran:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("pipeline worker shutting down: worker_id=%s", worker_id)


if __name__ == "__main__":
    from services.intelligence.ollama_client import OllamaClient
    from services.intelligence.repository import IntelligenceRepository
    from services.intelligence.worker import IntelligenceWorker
    from services.search.factory import build_encoder
    from services.search.meili_provider import MeilisearchSearchProvider
    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url)
    meili_provider = None
    if settings.feature_meilisearch_search or settings.feature_meilisearch_shadow_index:
        import meilisearch

        meili_client = meilisearch.Client(
            settings.meilisearch_url,
            api_key=settings.meilisearch_master_key,
        )
        meili_provider = MeilisearchSearchProvider(meili_client)

    with engine.connect() as conn:
        doc_repo = DocumentRepository(conn)
        es_client = ElasticsearchSearchClient(hosts=[settings.elastic_url])
        translator = LibreTranslateClient(base_url=settings.libretranslate_url)
        encoder = build_encoder(settings)
        qdrant_client = QdrantSearchClient(url=settings.qdrant_url, dimension=encoder.dimension)

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

        job_repo = PipelineJobRepository(conn)
        worker = PipelineWorker(
            document_repository=doc_repo,
            extractor_registry=ExtractorRegistry(),
            translator=translator,
            encoder=encoder,
            es_client=es_client,
            qdrant_client=qdrant_client,
            meili_provider=meili_provider,
            intelligence_worker=intelligence_worker,
            embedding_max_tokens=settings.embedding_max_tokens,
        )

        run_loop(job_repo, worker, conn, worker_id="pipeline-worker")
