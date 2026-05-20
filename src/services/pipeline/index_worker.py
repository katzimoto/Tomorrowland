"""Index worker that processes ``index_document`` jobs.

Claims durable index jobs from the queue, reads ``content_text`` and
``translated_text`` from ``document_payloads``, and indexes the document into
Elasticsearch. After successful text indexing, enqueues a
``vector_index_document`` job for the vector-worker to pick up.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from uuid import UUID

from services.documents.repository import DocumentRepository
from services.pipeline.jobs import PipelineJobRepository
from services.search.elastic import ElasticsearchSearchClient
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

_WORKER_TYPE = "index"
_ALLOWED_JOB_TYPES = ["index_document"]
_REAP_INTERVAL_SECONDS = 60.0


def run_index_once(
    job_repo: PipelineJobRepository,
    doc_repo: DocumentRepository,
    es_client: ElasticsearchSearchClient,
    worker_id: str = "index-worker",
    metrics: MetricsRegistry | None = None,
) -> bool:
    """Claim one ``index_document`` job and index it into Elasticsearch.

    Args:
        job_repo: Queue repository for claiming and updating jobs.
        doc_repo: Document repository for document metadata and group IDs.
        es_client: Elasticsearch client for text indexing.
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
    source_id: UUID = claimed["source_id"]

    if metrics is not None:
        metrics.pipeline_jobs_claimed_total.labels(
            worker_type=_WORKER_TYPE, job_type=job_type
        ).inc()

    job_repo.mark_running_stage(job_id, "index")

    start = time.monotonic()
    try:
        doc = doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        allowed_group_ids = [str(gid) for gid in doc_repo.source_group_ids(source_id)]

        payload = job_repo.get_payload(document_id)
        content_original = (payload["content_text"] if payload else None) or ""
        content_english = (payload["translated_text"] if payload else None) or content_original
        translation_quality: str | None = "fast" if content_english != content_original else None

        es_client.index_document(
            str(document_id),
            {
                "document_id": str(document_id),
                "path": doc.path or "",
                "filename": Path(doc.path).name if doc.path else doc.title or "",
                "content_original": content_original,
                "content_english": content_english,
                "title": doc.title or "",
                "summary": "",
                "tags": [],
                "metadata": doc.metadata,
                "allowed_group_ids": allowed_group_ids,
            },
        )

        doc_repo.update_indexed(document_id, "indexed", translation_quality)

    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        doc_repo.update_status(document_id, "failed")
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="index")
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="index",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "index job retried: worker_id=%s job_type=%s job_id=%s "
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
                    stage="index",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "index job dead-lettered: worker_id=%s job_type=%s job_id=%s "
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
            stage="index",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "index job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )

    try:
        job_repo.enqueue_document(
            document_id=document_id,
            source_id=source_id,
            job_type="vector_index_document",
        )
        logger.debug(
            "vector job enqueued: worker_id=%s document_id=%s",
            worker_id,
            document_id,
        )
    except Exception:
        logger.exception(
            "failed to enqueue vector job: worker_id=%s error_type=EnqueueError",
            worker_id,
        )

    return True


def run_index_loop(
    job_repo: PipelineJobRepository,
    doc_repo: DocumentRepository,
    es_client: ElasticsearchSearchClient,
    worker_id: str = "index-worker",
    poll_interval: float = 1.0,
    metrics: MetricsRegistry | None = None,
) -> None:
    """Run ``run_index_once`` in a loop until interrupted."""
    logger.info(
        "index worker started: worker_id=%s poll_interval=%.1f",
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
                        "stale index locks reaped: worker_id=%s count=%d",
                        worker_id,
                        reaped,
                    )

            try:
                ran = run_index_once(
                    job_repo,
                    doc_repo,
                    es_client,
                    worker_id=worker_id,
                    metrics=metrics,
                )
            except Exception as exc:
                error_type = type(exc).__name__
                if metrics is not None:
                    metrics.worker_loop_errors_total.labels(
                        worker_type=_WORKER_TYPE, error_type=error_type
                    ).inc()
                logger.exception(
                    "unhandled index loop error: worker_id=%s error_type=%s",
                    worker_id,
                    error_type,
                )
                time.sleep(poll_interval)
                continue

            if not ran:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("index worker shutting down: worker_id=%s", worker_id)


if __name__ == "__main__":
    from sqlalchemy import create_engine

    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url)

    with engine.begin() as conn:
        job_repo = PipelineJobRepository(conn)
        doc_repo = DocumentRepository(conn)
        es_client = ElasticsearchSearchClient(hosts=[settings.elastic_url])

        run_index_loop(job_repo, doc_repo, es_client, worker_id="index-worker")
