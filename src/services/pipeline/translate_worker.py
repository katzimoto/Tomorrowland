"""Translate stage consumer — translates extracted text and publishes embed."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.translation.client import LibreTranslateClient


class TranslateConsumer(BaseConsumer):
    queue_name = "document.translate.requested"
    worker_type = "translate-worker"

    def __init__(
        self,
        rabbit: Any,
        job_repo: PipelineJobRepository,
        publisher: DocumentPublisher,
        translator: LibreTranslateClient | None = None,
        health_port: int = 8080,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._publisher = publisher
        self._translator = translator

    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
    ) -> None:
        payload = self._job_repo.get_payload(document_id)
        content_text = (payload.get("content_text", "") if payload else None) or ""
        if not content_text:
            self._publisher.publish_embed(
                job_id=job_id,
                document_id=document_id,
                source_id=source_id,
                attempt=attempt,
            )
            return

        translated_text = content_text
        if self._translator:
            lang = payload.get("source_language") if payload else None
            if lang == "":
                lang = None
            translated_text = (
                self._translator.translate(content_text, source_lang=lang, target_lang="en")
                or content_text
            )

        self._job_repo.update_translated_text(document_id, translated_text)
        self._job_repo.mark_running_stage(job_id, "translated")
        self._publisher.publish_embed(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.pipeline.jobs import PipelineJobRepository
    from services.pipeline.publisher import DocumentPublisher
    from services.translation.client import LibreTranslateClient
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    connection = engine.connect()
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=settings.rabbitmq_enabled)
    job_repo = PipelineJobRepository(connection)
    publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
    translator = LibreTranslateClient(base_url=settings.libretranslate_url)
    consumer = TranslateConsumer(
        rabbit=rabbit, job_repo=job_repo, publisher=publisher, translator=translator
    )
    consumer.run()
