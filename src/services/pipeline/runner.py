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
from uuid import UUID

from sqlalchemy import create_engine

from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.worker import PipelineWorker
from services.search.elastic import ElasticsearchSearchClient
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient

logger = logging.getLogger(__name__)


def run_once(
    job_repo: PipelineJobRepository,
    worker: PipelineWorker,
    worker_id: str = "worker-default",
) -> bool:
    """Claim one job, process it, and mark it done.

    Args:
        job_repo: Queue repository for claiming and updating jobs.
        worker: Pipeline worker for document processing.
        worker_id: Identifier stamped on claimed jobs (for stale-lock tracking).

    Returns:
        ``True`` if a job was claimed and processed, ``False`` if no job was available.
    """
    claimed = job_repo.claim_next(worker_id)
    if claimed is None:
        return False

    job_id: UUID = claimed["id"]
    doc_id: UUID = claimed["doc_id"]
    attempts: int = claimed["attempts"]
    max_attempts: int = claimed["max_attempts"]

    # Load durable payload
    payload = job_repo.get_payload(doc_id)
    pre_extracted_text: str | None = payload["content_text"] if payload else None

    job_repo.mark_running_stage(job_id, "process")

    try:
        worker.process_document(doc_id, pre_extracted_text=pre_extracted_text)
    except Exception as exc:
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="process")
            logger.info("Job %s scheduled for retry (%d/%d)", job_id, attempts, max_attempts)
        else:
            job_repo.mark_dead_letter(job_id, exc)
            logger.warning("Job %s moved to dead-letter after %d attempts", job_id, attempts)
        return True

    job_repo.mark_succeeded(job_id)
    logger.info("Job %s completed successfully", job_id)

    # Enqueue vector indexing job after successful text processing
    if claimed["job_type"] == "process_document":
        try:
            job_repo.enqueue_document(
                doc_id=doc_id,
                source_id=claimed["source_id"],
                job_type="vector_index_document",
            )
            logger.debug("Vector job enqueued for doc %s", doc_id)
        except Exception:
            logger.exception("Failed to enqueue vector job for doc %s", doc_id)

    return True


def run_loop(
    job_repo: PipelineJobRepository,
    worker: PipelineWorker,
    worker_id: str = "worker-default",
    poll_interval: float = 1.0,
) -> None:
    """Run ``run_once`` in a loop until interrupted."""
    logger.info("Pipeline worker %s started (poll interval %.1fs)", worker_id, poll_interval)
    try:
        while True:
            ran = run_once(job_repo, worker, worker_id=worker_id)
            if not ran:
                import time

                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Pipeline worker %s shutting down", worker_id)


if __name__ == "__main__":
    from services.search.factory import build_encoder
    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.database_url)

    with engine.begin() as conn:
        doc_repo = DocumentRepository(conn)
        es_client = ElasticsearchSearchClient(hosts=[settings.elastic_url])
        qdrant_client = QdrantSearchClient(url=settings.qdrant_url)
        translator = LibreTranslateClient(base_url=settings.libretranslate_url)
        encoder = build_encoder(settings)

        job_repo = PipelineJobRepository(conn)
        worker = PipelineWorker(
            document_repository=doc_repo,
            extractor_registry=ExtractorRegistry(),
            translator=translator,
            encoder=encoder,
            es_client=es_client,
            qdrant_client=qdrant_client,
        )

        run_loop(job_repo, worker, worker_id="pipeline-worker")
