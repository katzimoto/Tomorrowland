"""Embed stage consumer — chunks + vectorizes text and publishes index."""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.search.encoder import TextEncoder
from services.search.qdrant import QdrantSearchClient

_log = logging.getLogger(__name__)


def _warmup_encoder(
    encoder: TextEncoder,
    retries: int = 5,
    delay: float = 10.0,
) -> None:
    """Pre-load the embedding model before the worker starts consuming.

    Ollama loads models from disk on the first request, which can take longer
    than the per-job timeout.  Calling encode() here — before any real job
    arrives — absorbs that cold-start latency without burning a retry attempt.
    If warmup fails after all retries (e.g. Ollama is still starting), we log
    an error and proceed; the first job will go through the normal retry path.
    """
    for attempt in range(1, retries + 1):
        try:
            encoder.encode("warmup")
            _log.info("embed-worker: encoder ready (warmup attempt %d)", attempt)
            return
        except Exception as exc:
            if attempt < retries:
                _log.warning(
                    "embed-worker: warmup attempt %d/%d failed, retrying in %.0fs: %s",
                    attempt,
                    retries,
                    delay,
                    exc,
                )
                time.sleep(delay)
            else:
                _log.error(
                    "embed-worker: encoder warmup failed after %d attempts — "
                    "first job may still encounter a cold-start timeout: %s",
                    retries,
                    exc,
                )


class EmbedConsumer(BaseConsumer):
    queue_name = "document.embed.requested"
    worker_type = "embed-worker"

    def __init__(
        self,
        rabbit: Any,
        job_repo: PipelineJobRepository,
        doc_repo: DocumentRepository,
        publisher: DocumentPublisher,
        encoder: TextEncoder,
        qdrant: QdrantSearchClient,
        embedding_max_tokens: int | None = None,
        health_port: int = 8080,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._doc_repo = doc_repo
        self._publisher = publisher
        self._encoder = encoder
        self._qdrant = qdrant
        self._embedding_max_tokens = embedding_max_tokens

    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
        content_text: str = "",
        translated_text: str = "",
    ) -> None:
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        allowed_group_ids = [str(gid) for gid in self._doc_repo.source_group_ids(source_id)]

        chunk_texts: list[str] = []
        chunk_meta: list[dict[str, Any]] = []

        for idx, chunk in enumerate(
            chunk_text(
                content_text,
                language=doc.source_language,
                max_tokens=self._embedding_max_tokens,
            )
        ):
            chunk_texts.append(chunk)
            chunk_meta.append({"lang": doc.source_language, "suffix": "orig", "idx": idx})

        for idx, chunk in enumerate(
            chunk_text(
                translated_text,
                language=doc.target_language,
                max_tokens=self._embedding_max_tokens,
            )
        ):
            chunk_texts.append(chunk)
            chunk_meta.append({"lang": doc.target_language, "suffix": "tr", "idx": idx})

        vectors = self._encoder.encode_batch(chunk_texts)

        qdrant_chunks: list[dict[str, Any]] = []
        for i, meta in enumerate(chunk_meta):
            entry: dict[str, Any] = {
                "chunk_id": f"{document_id}-{meta['suffix']}-{meta['idx']}",
                "document_id": str(document_id),
                "group_id": allowed_group_ids,
                "chunk_index": meta["idx"],
                "text": chunk_texts[i],
                "vector": vectors[i],
                "source_id": str(source_id),
            }
            if doc.title:
                entry["title"] = doc.title
            if meta["lang"]:
                entry["language"] = meta["lang"]
            qdrant_chunks.append(entry)

        if qdrant_chunks:
            self._qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)

        self._job_repo.mark_running_stage(job_id, "embedded")
        self._job_repo.commit()
        self._publisher.publish_index(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated_text,
        )


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.documents.repository import DocumentRepository
    from services.pipeline.jobs import PipelineJobRepository
    from services.pipeline.publisher import DocumentPublisher
    from services.search.factory import build_encoder
    from services.search.qdrant import QdrantSearchClient
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    connection = engine.connect()
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
    job_repo = PipelineJobRepository(connection)
    doc_repo = DocumentRepository(connection)
    publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
    encoder = build_encoder(settings)
    _warmup_encoder(encoder)
    qdrant = QdrantSearchClient(url=settings.qdrant_url, dimension=encoder.dimension)
    consumer = EmbedConsumer(
        rabbit=rabbit,
        job_repo=job_repo,
        doc_repo=doc_repo,
        publisher=publisher,
        encoder=encoder,
        qdrant=qdrant,
        embedding_max_tokens=settings.embedding_max_tokens,
    )
    consumer.run()
