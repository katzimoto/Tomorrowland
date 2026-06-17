"""Embed stage consumer — chunks + vectorizes text and publishes index."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from services.chunking.splitter import chunk_text, resolve_chunk_locations
from services.documents.layout_block_repository import LayoutBlockRepository
from services.documents.repository import DocumentRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.search.encoder import TextEncoder
from services.search.qdrant import QdrantSearchClient

logger = logging.getLogger(__name__)


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
                    "text_lane": "original",
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
                        "text_lane": "translated",
                        "source_lang": doc.source_language,
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
            entry["text_lane"] = meta["text_lane"]
            if meta.get("source_lang"):
                entry["translated_from"] = meta["source_lang"]
            if meta.get("page_number") is not None:
                entry["page_number"] = meta["page_number"]
            if meta.get("section_heading") is not None:
                entry["section_heading"] = meta["section_heading"]
            qdrant_chunks.append(entry)

        if qdrant_chunks:
            # PR3: resolve layout_block_id for precise chunk→block linkage.
            # Layout blocks are written by parse_worker before embed runs,
            # so they should exist for most documents.
            from services.rag.layout_hierarchy import resolve_chunk_layout_block_ids

            try:
                layout_repo = LayoutBlockRepository(self._doc_repo._connection)
                resolve_chunk_layout_block_ids(qdrant_chunks, document_id, layout_repo)
            except Exception:
                logger.debug(
                    "layout_block_id resolution skipped for document_id=%s",
                    document_id,
                )

            self._qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)

        self._job_repo.mark_running_stage(job_id, "embedded")
        # Final index pass (enrich=True): refreshes Meilisearch and fires
        # intelligence/alert exactly once, on the post-translation content
        # (#694). The translate stage's earlier pass used enrich=False.
        self._publisher.publish_index(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated_text,
            enrich=True,
        )


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.documents.repository import DocumentRepository
    from services.intelligence.task_defaults import build_task_resolver
    from services.pipeline.jobs import PipelineJobRepository
    from services.pipeline.publisher import DocumentPublisher
    from services.search.factory import build_encoder
    from services.search.qdrant import QdrantSearchClient
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    resolver = build_task_resolver(engine, settings)
    connection = engine.connect()
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
    job_repo = PipelineJobRepository(connection)
    doc_repo = DocumentRepository(connection)
    publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
    encoder = build_encoder(settings, resolver=resolver)
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
