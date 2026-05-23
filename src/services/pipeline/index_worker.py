"""Index stage consumer — indexes document in Elasticsearch and publishes downstream."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from services.documents.repository import DocumentRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.search.elastic import ElasticsearchSearchClient


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
        health_port: int = 8080,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._doc_repo = doc_repo
        self._publisher = publisher
        self._es = es_client

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
        body: dict[str, Any] = {
            "document_id": str(document_id),
            "source_id": str(source_id),
            "title": doc.title or "",
            "mime_type": doc.mime_type,
            "source": str(doc.source),
            "source_language": doc.source_language or "",
            "target_language": doc.target_language,
        }
        if payload:
            if payload.get("content_text"):
                body["content_text"] = payload["content_text"]
            if payload.get("translated_text"):
                body["translated_text"] = payload["translated_text"]

        self._es.index_document(str(document_id), body)

        self._job_repo.mark_running_stage(job_id, "indexed")
        self._job_repo.mark_succeeded(job_id)


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
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=settings.rabbitmq_enabled)
    job_repo = PipelineJobRepository(connection)
    doc_repo = DocumentRepository(connection)
    publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
    es_client = ElasticsearchSearchClient(hosts=[settings.elastic_url])
    consumer = IndexConsumer(
        rabbit=rabbit,
        job_repo=job_repo,
        doc_repo=doc_repo,
        publisher=publisher,
        es_client=es_client,
    )
    consumer.run()
