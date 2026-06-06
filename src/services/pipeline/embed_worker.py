"""Embed stage consumer — chunks + vectorizes text and publishes index."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from services.chunking.splitter import chunk_text, resolve_chunk_locations
from services.documents.repository import DocumentRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.search.encoder import TextEncoder
from services.search.qdrant import QdrantSearchClient


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
        health_port: int = 8083,
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

        payload = self._job_repo.get_payload(document_id)
        extraction_metadata = payload.get("extraction_metadata") if payload else None

        allowed_group_ids = [str(gid) for gid in self._doc_repo.source_group_ids(source_id)]

        # Chunk original text
        original_chunks = list(
            chunk_text(
                content_text,
                language=doc.source_language,
                max_tokens=self._embedding_max_tokens,
            )
        )

        # Resolve page/section location metadata for original chunks
        orig_locations = resolve_chunk_locations(
            content_text, original_chunks, extraction_metadata or []
        )

        chunk_texts: list[str] = []
        chunk_meta: list[dict[str, Any]] = []

        for idx, chunk in enumerate(original_chunks):
            chunk_texts.append(chunk)
            loc = orig_locations[idx] if idx < len(orig_locations) else {}
            chunk_meta.append(
                {
                    "lang": doc.source_language,
                    "suffix": "orig",
                    "idx": idx,
                    "page_number": loc.get("page_number"),
                    "section_heading": loc.get("section_heading"),
                }
            )

        # Only chunk+embed translated text when it differs from the original.
        # Embedding identical text produces duplicate vectors that pollute
        # the vector space without adding retrieval value.
        if translated_text and translated_text != content_text:
            for idx, chunk in enumerate(
                chunk_text(
                    translated_text,
                    language=doc.target_language,
                    max_tokens=self._embedding_max_tokens,
                )
            ):
                chunk_texts.append(chunk)
                chunk_meta.append(
                    {
                        "lang": doc.target_language,
                        "suffix": "tr",
                        "idx": idx,
                        "page_number": None,
                        "section_heading": None,
                    }
                )

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
            if meta.get("page_number") is not None:
                entry["page_number"] = meta["page_number"]
            if meta.get("section_heading") is not None:
                entry["section_heading"] = meta["section_heading"]
            qdrant_chunks.append(entry)

        if qdrant_chunks:
            self._qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)

        self._job_repo.mark_running_stage(job_id, "embedded")
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
