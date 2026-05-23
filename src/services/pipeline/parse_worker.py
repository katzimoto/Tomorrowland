"""Parse stage consumer — extracts text from a document and publishes translate."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from services.documents.repository import DocumentRepository
from services.extraction.registry import ExtractorRegistry
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher


class ParseConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def __init__(
        self,
        rabbit,
        job_repo: PipelineJobRepository,
        doc_repo: DocumentRepository,
        publisher: DocumentPublisher,
        extractor: ExtractorRegistry | None = None,
        health_port: int = 8080,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._doc_repo = doc_repo
        self._publisher = publisher
        self._extractor = extractor or ExtractorRegistry()

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
        if not content_text and doc.path:
            content_text = self._extractor.extract(Path(doc.path), doc.mime_type)

        self._job_repo.update_content_text(document_id, content_text)
        self._job_repo.mark_running_stage(job_id, "parsed")
        self._publisher.publish_translate(
            job_id=job_id, document_id=document_id, source_id=source_id, attempt=attempt
        )


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.documents.repository import DocumentRepository
    from services.pipeline.jobs import PipelineJobRepository
    from services.pipeline.publisher import DocumentPublisher
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
    consumer = ParseConsumer(
        rabbit=rabbit, job_repo=job_repo, doc_repo=doc_repo, publisher=publisher
    )
    consumer.run()
