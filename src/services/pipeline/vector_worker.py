"""Vector indexing worker that processes ``vector_index_document`` jobs.

Claims durable vector jobs from the queue, encodes chunks via Ollama,
and writes Qdrant points. Independent of the text pipeline worker.
"""

from __future__ import annotations

import logging
from uuid import UUID

from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.pipeline.jobs import PipelineJobRepository
from services.search.encoder import TextEncoder as _TProto
from services.search.qdrant import QdrantSearchClient

logger = logging.getLogger(__name__)


def run_vector_once(
    job_repo: PipelineJobRepository,
    encoder: _TProto,
    qdrant: QdrantSearchClient,
    doc_repo: DocumentRepository,
    extractor: ExtractorRegistry,
    worker_id: str = "vector-worker",
) -> bool:
    """Claim one vector job, encode chunks, and upsert Qdrant points.

    Args:
        job_repo: Queue repository.
        encoder: Text encoder (Ollama or test).
        qdrant: Qdrant client.
        doc_repo: Document repository for source group IDs.
        extractor: Extractor registry for file content.
        worker_id: Identifier for lock tracking.

    Returns:
        ``True`` if a job was processed, ``False`` if none available.
    """
    claimed = job_repo.claim_next(worker_id, job_types=["vector_index_document"])
    if claimed is None:
        return False

    job_id: UUID = claimed["id"]
    doc_id: UUID = claimed["doc_id"]
    attempts: int = claimed["attempts"]
    max_attempts: int = claimed["max_attempts"]
    source_id: UUID = claimed["source_id"]

    job_repo.mark_running_stage(job_id, "vector_encode")

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
        qdrant_chunks: list[dict] = []
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
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="vector_encode")
            logger.info("Vector job %s scheduled for retry (%d/%d)", job_id, attempts, max_attempts)
        else:
            job_repo.mark_dead_letter(job_id, exc)
            logger.warning("Vector job %s dead-lettered after %d attempts", job_id, attempts)
        return True

    job_repo.mark_succeeded(job_id)
    logger.info("Vector job %s completed", job_id)
    return True


if __name__ == "__main__":
    from sqlalchemy import create_engine

    from services.search.factory import build_encoder
    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.database_url)

    with engine.begin() as conn:
        job_repo = PipelineJobRepository(conn)
        encoder = build_encoder(settings)
        qdrant = QdrantSearchClient(url=settings.qdrant_url)
        doc_repo = DocumentRepository(conn)
        extractor = ExtractorRegistry()

        import time

        try:
            while True:
                ran = run_vector_once(job_repo, encoder, qdrant, doc_repo, extractor)
                if not ran:
                    time.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("Vector worker shutting down")
