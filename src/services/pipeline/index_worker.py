"""Index stage consumer — indexes document in Elasticsearch and Meilisearch."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from services.chunking.splitter import chunk_text
from services.documents.repository import DocumentRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.search.elastic import ElasticsearchSearchClient
from services.search.meili_provider import MeilisearchSearchProvider
from services.search.meili_types import ChunkMetadata, SearchChunkRecord


class IndexConsumer(BaseConsumer):
    queue_name = "document.index.requested"
    worker_type = "index-worker"

    def __init__(
        self,
        rabbit: Any,
        job_repo: PipelineJobRepository,
        doc_repo: DocumentRepository,
        publisher: DocumentPublisher,
        es_client: ElasticsearchSearchClient,
        meili: MeilisearchSearchProvider | None = None,
        embedding_max_tokens: int | None = None,
        health_port: int = 8080,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._doc_repo = doc_repo
        self._publisher = publisher
        self._es = es_client
        self._meili = meili
        self._embedding_max_tokens = embedding_max_tokens

    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
    ) -> None:
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        payload = self._job_repo.get_payload(document_id)
        content_text = (payload.get("content_text", "") if payload else None) or ""
        translated_text = (payload.get("translated_text", "") if payload else None) or ""
        allowed_group_ids = [str(gid) for gid in self._doc_repo.source_group_ids(source_id)]

        body: dict[str, Any] = {
            "document_id": str(document_id),
            "source_id": str(source_id),
            "title": doc.title or "",
            "mime_type": doc.mime_type,
            "source": str(doc.source),
            "source_language": doc.source_language or "",
            "target_language": doc.target_language,
        }
        if content_text:
            body["content_text"] = content_text
        if translated_text:
            body["translated_text"] = translated_text

        self._es.index_document(str(document_id), body)

        if self._meili is not None and content_text:
            self._index_meili(
                document_id, doc, content_text, translated_text, allowed_group_ids
            )

        self._job_repo.mark_running_stage(job_id, "indexed")
        self._publisher.publish_intelligence(
            job_id=job_id, document_id=document_id, source_id=source_id, attempt=attempt
        )
        self._publisher.publish_alert(
            job_id=job_id, document_id=document_id, source_id=source_id, attempt=attempt
        )
        self._job_repo.mark_succeeded(job_id)

    def _index_meili(
        self,
        document_id: UUID,
        doc: Any,
        content_text: str,
        translated_text: str,
        allowed_group_ids: list[str],
    ) -> None:
        original_chunks = list(
            chunk_text(
                content_text,
                language=doc.source_language,
                max_tokens=self._embedding_max_tokens,
            )
        )
        translated_chunks = (
            list(
                chunk_text(
                    translated_text,
                    language=doc.target_language,
                    max_tokens=self._embedding_max_tokens,
                )
            )
            if translated_text and translated_text != content_text
            else []
        )

        pair_count = min(len(original_chunks), len(translated_chunks)) if translated_chunks else 0
        records: list[SearchChunkRecord] = []

        for idx in range(pair_count):
            records.append(
                SearchChunkRecord.from_parts(
                    document_id=str(document_id),
                    chunk_index=idx,
                    title=doc.title or "",
                    content=original_chunks[idx],
                    allowed_group_ids=allowed_group_ids,
                    metadata=ChunkMetadata(
                        source=doc.source,
                        mime_type=doc.mime_type,
                        language=doc.source_language,
                    ),
                    content_en=translated_chunks[idx],
                )
            )

        for idx in range(pair_count, len(original_chunks)):
            records.append(
                SearchChunkRecord.from_parts(
                    document_id=str(document_id),
                    chunk_index=idx,
                    title=doc.title or "",
                    content=original_chunks[idx],
                    allowed_group_ids=allowed_group_ids,
                    metadata=ChunkMetadata(
                        source=doc.source,
                        mime_type=doc.mime_type,
                        language=doc.source_language,
                    ),
                    content_en=None,
                )
            )

        if records:
            self._meili.index_batch(records)


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.documents.repository import DocumentRepository
    from services.pipeline.jobs import PipelineJobRepository
    from services.pipeline.publisher import DocumentPublisher
    from services.search.elastic import ElasticsearchSearchClient
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
    es_client = ElasticsearchSearchClient(hosts=[settings.elastic_url])

    meili = None
    if settings.feature_meilisearch_search or settings.feature_meilisearch_shadow_index:
        import meilisearch

        meili_client = meilisearch.Client(
            settings.meilisearch_url,
            api_key=settings.meilisearch_master_key,
        )
        meili = MeilisearchSearchProvider(meili_client)

    consumer = IndexConsumer(
        rabbit=rabbit,
        job_repo=job_repo,
        doc_repo=doc_repo,
        publisher=publisher,
        es_client=es_client,
        meili=meili,
        embedding_max_tokens=settings.embedding_max_tokens,
    )
    consumer.run()
