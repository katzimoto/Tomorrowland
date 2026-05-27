"""Vector indexing worker that processes ``vector_index_document`` jobs.

Claims durable vector jobs from the queue, encodes chunks via Ollama,
and writes Qdrant points for both original and translated text.
Independent of the text pipeline worker.
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
_ALLOWED_JOB_TYPES = ["vector_index_document"]
_REAP_INTERVAL_SECONDS = 60.0


def run_vector_once(
    job_repo: PipelineJobRepository,
    encoder: _TProto,
    qdrant: QdrantSearchClient,
    doc_repo: DocumentRepository,
    extractor: ExtractorRegistry,
    worker_id: str = "vector-worker",
    metrics: MetricsRegistry | None = None,
    embedding_max_tokens: int | None = None,
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
        embedding_max_tokens: Maximum estimated tokens per chunk before encoding.
            Passed to chunking to prevent embedding context-length errors.

    Returns:
        ``True`` if a job was processed, ``False`` if none available.
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

    job_repo.mark_running_stage(job_id, "vector_encode")

    start = time.monotonic()
    try:
        doc = doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        allowed_group_ids = [str(gid) for gid in doc_repo.source_group_ids(source_id)]

        # Load payload texts for chunking
        payload = job_repo.get_payload(document_id)
        content_text = (payload.get("content_text", "") if payload else None) or ""
        if not content_text and doc.path:
            from pathlib import Path

            content_text = extractor.extract(Path(doc.path), doc.mime_type)

        translated_text = (payload.get("translated_text", "") if payload else None) or ""

        # Helper to build a single Qdrant chunk entry
        def _build_chunk(
            chunk_text_content: str,
            vector: list[float],
            idx: int,
            *,
            lang: str | None,
            suffix: str,
        ) -> dict[str, Any]:
            entry: dict[str, Any] = {
                "chunk_id": f"{document_id}-{suffix}-{idx}",
                "document_id": str(document_id),
                "group_id": allowed_group_ids,
                "chunk_index": idx,
                "text": chunk_text_content,
                "vector": vector,
                "source_id": str(source_id),
            }
            if doc.title:
                entry["title"] = doc.title
            if lang:
                entry["language"] = lang
            return entry

        qdrant_chunks: list[dict[str, Any]] = []

        # Collect all chunk texts first
        chunk_texts: list[str] = []
        chunk_meta: list[dict[str, Any]] = []

        # Original language chunks
        for idx, chunk_text_content in enumerate(
            chunk_text(
                content_text,
                language=doc.source_language,
                max_tokens=embedding_max_tokens,
            )
        ):
            chunk_texts.append(chunk_text_content)
            chunk_meta.append(
                {
                    "lang": doc.source_language,
                    "suffix": "orig",
                    "idx": idx,
                }
            )

        # Translated chunks (when translation exists and differs from original)
        if translated_text and translated_text != content_text:
            for idx, chunk_text_content in enumerate(
                chunk_text(
                    translated_text,
                    language=doc.target_language,
                    max_tokens=embedding_max_tokens,
                )
            ):
                chunk_texts.append(chunk_text_content)
                chunk_meta.append(
                    {
                        "lang": doc.target_language,
                        "suffix": "tr",
                        "idx": idx,
                    }
                )

        # Batch-encode all chunks in a single Ollama call
        vectors = encoder.encode_batch(chunk_texts)

        # Build Qdrant entries with pre-computed vectors
        for i, meta in enumerate(chunk_meta):
            qdrant_chunks.append(
                _build_chunk(
                    chunk_texts[i],
                    vectors[i],
                    meta["idx"],
                    lang=meta["lang"],
                    suffix=meta["suffix"],
                )
            )

        if qdrant_chunks:
            # Delete stale chunks from previous indexing runs before upserting
            # so re-indexed documents with fewer chunks don't leave orphaned points.
            qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)

    except ValueError as exc:
        # Embedding context-length errors are permanent — retrying won't help.
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
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
            "vector job dead-lettered (permanent error): worker_id=%s job_type=%s job_id=%s "
            "attempts=%d error_type=%s error=%s",
            worker_id,
            job_type,
            job_id,
            attempts,
            error_type,
            exc,
        )
        return True

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
    conn: Connection,
    worker_id: str = "vector-worker",
    poll_interval: float = 1.0,
    metrics: MetricsRegistry | None = None,
    embedding_max_tokens: int | None = None,
) -> None:
    """Run ``run_vector_once`` in a loop until interrupted.

    Emits a heartbeat gauge and queue-depth snapshot each iteration.
    Reaps stale locks every ``_REAP_INTERVAL_SECONDS`` seconds.
    Each iteration runs in its own short transaction so other
    processes (API, pipeline runner) see results immediately.
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
                    embedding_max_tokens=embedding_max_tokens,
                )
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
    from sqlalchemy.engine import Connection

    from services.search.factory import build_encoder
    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url)

    with engine.connect() as conn:
        job_repo = PipelineJobRepository(conn)
        encoder = build_encoder(settings)
        qdrant = QdrantSearchClient(url=settings.qdrant_url, dimension=encoder.dimension)
        doc_repo = DocumentRepository(conn)
        extractor = ExtractorRegistry(
            enable_ocr=settings.enable_ocr,
            enable_legacy_office=settings.enable_legacy_office,
        )

        run_vector_loop(
            job_repo,
            encoder,
            qdrant,
            doc_repo,
            extractor,
            conn,
            embedding_max_tokens=settings.embedding_max_tokens,
        )
