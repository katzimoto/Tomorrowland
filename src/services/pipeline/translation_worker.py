"""Translation worker that processes ``translate_document`` jobs.

Claims durable translation jobs from the queue, reads raw ``content_text``
from ``document_payloads``, translates via LibreTranslate, and persists
``translated_text`` back to the payload table so the index-worker can
consume it without re-running translation.

After a successful translation the worker publishes embed and index messages
to RabbitMQ so the async pipeline (EmbedConsumer → IndexConsumer) picks them
up. The previous behaviour of enqueuing an orphan ``index_document`` database
job has been removed — no worker processed those jobs, leaving translated
documents permanently unindexed.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from services.documents.repository import DocumentRepository
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.translation.client import LibreTranslateClient
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

_WORKER_TYPE = "translation"
_ALLOWED_JOB_TYPES = ["translate_document"]
_REAP_INTERVAL_SECONDS = 60.0


def run_translation_once(
    job_repo: PipelineJobRepository,
    doc_repo: DocumentRepository,
    translator: LibreTranslateClient,
    worker_id: str = "translation-worker",
    metrics: MetricsRegistry | None = None,
    publisher: DocumentPublisher | None = None,
) -> bool:
    """Claim one ``translate_document`` job, translate, and persist result.

    After a successful translation the embed + index stages are triggered via
    the RabbitMQ publisher (when available) rather than enqueuing an orphan
    ``index_document`` database job that no worker processes.

    Args:
        job_repo: Queue repository for claiming and updating jobs.
        doc_repo: Document repository for loading document metadata.
        translator: LibreTranslate client.
        worker_id: Identifier stamped on claimed jobs (for stale-lock tracking).
        metrics: Optional metrics registry; pass ``None`` to disable instrumentation.
        publisher: Optional RabbitMQ publisher. When provided, embed + index
            messages are published after translation. When ``None``, a warning
            is logged and downstream processing is skipped (legacy
            ``index_document`` database jobs are no longer enqueued).

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
    source_id: UUID = claimed["source_id"]

    if metrics is not None:
        metrics.pipeline_jobs_claimed_total.labels(
            worker_type=_WORKER_TYPE, job_type=job_type
        ).inc()

    job_repo.mark_running_stage(job_id, "translate")

    start = time.monotonic()
    try:
        doc = doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        payload = job_repo.get_payload(document_id)
        content_text = (payload["content_text"] if payload else None) or ""
        if not content_text:
            # Document has no extractable text (e.g. scanned PDF without OCR,
            # empty file).  Skip translation gracefully — raising here would
            # retry and dead-letter a valid document.
            logger.info("translation skipped: empty content_text document_id=%s", document_id)
            job_repo.update_translated_text(document_id, "")
            job_repo.mark_succeeded(job_id)
            _publish_downstream(publisher, job_id, document_id, source_id, 1, "", "")
            return True

        translated = translator.translate(content_text, source_lang=doc.source_language)
        job_repo.update_translated_text(document_id, translated)

    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="translate")
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="translate",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "translation job retried: worker_id=%s job_type=%s job_id=%s "
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
                    stage="translate",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "translation job dead-lettered: worker_id=%s job_type=%s job_id=%s "
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
            stage="translate",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "translation job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )

    _publish_downstream(publisher, job_id, document_id, source_id, attempts, content_text, translated)

    return True


def run_translation_loop(
    job_repo: PipelineJobRepository,
    doc_repo: DocumentRepository,
    translator: LibreTranslateClient,
    worker_id: str = "translation-worker",
    poll_interval: float = 1.0,
    metrics: MetricsRegistry | None = None,
    publisher: DocumentPublisher | None = None,
) -> None:
    """Run ``run_translation_once`` in a loop until interrupted."""
    logger.info(
        "translation worker started: worker_id=%s poll_interval=%.1f",
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
                        "stale translation locks reaped: worker_id=%s count=%d",
                        worker_id,
                        reaped,
                    )

            try:
                ran = run_translation_once(
                    job_repo,
                    doc_repo,
                    translator,
                    worker_id=worker_id,
                    metrics=metrics,
                    publisher=publisher,
                )
            except Exception as exc:
                error_type = type(exc).__name__
                if metrics is not None:
                    metrics.worker_loop_errors_total.labels(
                        worker_type=_WORKER_TYPE, error_type=error_type
                    ).inc()
                logger.exception(
                    "unhandled translation loop error: worker_id=%s error_type=%s",
                    worker_id,
                    error_type,
                )
                time.sleep(poll_interval)
                continue

            if not ran:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("translation worker shutting down: worker_id=%s", worker_id)


def _publish_downstream(
    publisher: DocumentPublisher | None,
    job_id: UUID,
    document_id: UUID,
    source_id: UUID,
    attempt: int,
    content_text: str,
    translated_text: str,
) -> None:
    """Publish embed + index messages after translation completes.

    This replaces the legacy ``enqueue_document("index_document")`` pattern
    which created orphan database jobs that no worker processed.
    """
    if publisher is None:
        logger.warning(
            "no publisher available — downstream pipeline (embed/index) not "
            "triggered for document_id=%s. Translated text is persisted but "
            "will not be indexed until another pipeline run.",
            document_id,
        )
        return

    try:
        publisher.publish_embed(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated_text,
        )
        publisher.publish_index(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated_text,
        )
        logger.debug(
            "downstream pipeline triggered: worker_id=translation-worker "
            "document_id=%s job_id=%s",
            document_id,
            job_id,
        )
    except Exception:
        logger.exception(
            "failed to publish downstream messages for document_id=%s — "
            "translated text is persisted but embed/index may not run",
            document_id,
        )


if __name__ == "__main__":
    from sqlalchemy import create_engine

    from services.pipeline.publisher import DocumentPublisher
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    settings = Settings()
    engine = create_engine(settings.postgres_url)

    with engine.begin() as conn:
        job_repo = PipelineJobRepository(conn)
        doc_repo = DocumentRepository(conn)
        translator = LibreTranslateClient(base_url=settings.libretranslate_url)
        rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
        publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)

        run_translation_loop(
            job_repo,
            doc_repo,
            translator,
            worker_id="translation-worker",
            publisher=publisher,
        )
