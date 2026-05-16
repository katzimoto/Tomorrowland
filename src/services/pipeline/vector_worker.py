"""Vector indexing worker that processes ``vector_index_document`` jobs.

Claims durable vector jobs from the queue, encodes chunks via Ollama,
and writes Qdrant points. Independent of the text pipeline worker.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.pipeline.jobs import PipelineJobRepository
from services.search.encoder import TextEncoder as _TProto
from services.search.qdrant import QdrantSearchClient
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

_WORKER_TYPE = "vector"
_REAP_INTERVAL_SECONDS = 60.0


def run_vector_once(
    job_repo: PipelineJobRepository,
    encoder: _TProto,
    qdrant: QdrantSearchClient,
    doc_repo: DocumentRepository,
    extractor: ExtractorRegistry,
    worker_id: str = "vector-worker",
    metrics: MetricsRegistry | None = None,
) -> bool:
    """Claim one vector job, encode chunks, and upsert Qdrant points.

    Args:
        job_repo: Queue repository.
        encoder: Text encoder (Ollama or test).
        qdrant: Qdrant client.
        doc_repo: Document repository for source group IDs.
        extractor: Extractor registry for file content.
        worker_id: Identifier for lock tracking.
        metrics: Optional metrics registry; pass ``None`` to disable instrumentation.

    Returns:
        ``True`` if a job was processed, ``False`` if none available.
    """
    claimed = job_repo.claim_next(worker_id, job_types=["vector_index_document"])
    if claimed is None:
        return False

    job_id: UUID = claimed["id"]
    doc_id: UUID = claimed["doc_id"]
    job_type: str = claimed["job_type"]
    attempts: int = claimed["attempts"]
    max_attempts: int = claimed["max_attempts"]
    source_id: UUID = claimed["source_id"]

    if metrics is not None:
        metrics.pipeline_jobs_claimed_total.labels(
            worker_type=_WORKER_TYPE, job_type=job_type
        ).inc()

    job_repo.mark_running_stage(job_id, "vector_encode")

    start = time.monotonic()
    try:
        doc = doc_repo.get_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document {doc_id} not found")

        allowed_group_ids = [str(gid) for gid in doc_repo.source_group_ids(source_id)]

        # Load payload text for chunking
        payload = job_repo.get_payload(doc_id)
        content = (payload["content_text"] if payload else None) or ""
        if not content and doc.path:
            from pathlib import Path

            content = extractor.extract(Path(doc.path), doc.mime_type)

        chunks = chunk_text(content)
        qdrant_chunks: list[dict[str, Any]] = []
        for idx, chunk_text_content in enumerate(chunks):
            vector = encoder.encode(chunk_text_content)
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

        if qdrant_chunks:
            qdrant.upsert_chunks(qdrant_chunks)

    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="vector_encode")
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type=_WORKER_TYPE, job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type=_WORKER_TYPE,
                    job_type=job_type,
                    stage="vector_encode",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "vector job retried: worker_id=%s job_type=%s job_id=%s "
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
                    stage="vector_encode",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "vector job dead-lettered: worker_id=%s job_type=%s job_id=%s "
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
            stage="vector_encode",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "vector job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )
    return True


def run_vector_loop(
    job_repo: PipelineJobRepository,
    encoder: _TProto,
    qdrant: QdrantSearchClient,
    doc_repo: DocumentRepository,
    extractor: ExtractorRegistry,
    worker_id: str = "vector-worker",
    poll_interval: float = 1.0,
    metrics: MetricsRegistry | None = None,
) -> None:
    """Run ``run_vector_once`` in a loop until interrupted.

    Emits a heartbeat gauge and queue-depth snapshot each iteration.
    Reaps stale locks every ``_REAP_INTERVAL_SECONDS`` seconds.
    """
    logger.info(
        "vector worker started: worker_id=%s poll_interval=%.1f",
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
                        "stale vector locks reaped: worker_id=%s count=%d",
                        worker_id,
                        reaped,
                    )

            try:
                ran = run_vector_once(
                    job_repo,
                    encoder,
                    qdrant,
                    doc_repo,
                    extractor,
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
                    "unhandled vector loop error: worker_id=%s error_type=%s",
                    worker_id,
                    error_type,
                )
                time.sleep(poll_interval)
                continue

            if not ran:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("vector worker shutting down: worker_id=%s", worker_id)


if __name__ == "__main__":
    from sqlalchemy import create_engine

    from services.search.factory import build_encoder
    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url)

    with engine.begin() as conn:
        job_repo = PipelineJobRepository(conn)
        encoder = build_encoder(settings)
        qdrant = QdrantSearchClient(url=settings.qdrant_url)
        doc_repo = DocumentRepository(conn)
        extractor = ExtractorRegistry()

        run_vector_loop(job_repo, encoder, qdrant, doc_repo, extractor)
