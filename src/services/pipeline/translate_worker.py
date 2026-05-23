"""Translate stage consumer — translates extracted text and publishes embed."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from services.documents.repository import DocumentRepository, TranslationVersionRepository
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
        version_repo: TranslationVersionRepository | None = None,
        doc_repo: DocumentRepository | None = None,
        health_port: int = 8080,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._publisher = publisher
        self._translator = translator
        self._version_repo = version_repo
        self._doc_repo = doc_repo

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

        if self._doc_repo and translated_text and translated_text != content_text:
            self._doc_repo.update_indexed(document_id, "indexed", "fast")

        if self._version_repo and translated_text and translated_text != content_text:
            existing = self._version_repo.find_pending_or_running(document_id, "en")
            if existing is not None:
                self._version_repo.update_version_status(
                    UUID(str(existing["id"])),
                    "available",
                    translated_text=translated_text,
                )
            else:
                self._version_repo.create_version(
                    document_id=document_id,
                    label="Ingestion",
                    quality="fast",
                    request_type="ingestion",
                    target_language="en",
                )
                created = self._version_repo.find_pending_or_running(document_id, "en")
                if created is not None:
                    self._version_repo.update_version_status(
                        UUID(str(created["id"])),
                        "available",
                        translated_text=translated_text,
                    )

        self._publisher.publish_embed(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.documents.repository import DocumentRepository, TranslationVersionRepository
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
    doc_repo = DocumentRepository(connection)
    publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
    translator = LibreTranslateClient(base_url=settings.libretranslate_url)
    version_repo = TranslationVersionRepository(connection)
    consumer = TranslateConsumer(
        rabbit=rabbit,
        job_repo=job_repo,
        publisher=publisher,
        translator=translator,
        version_repo=version_repo,
        doc_repo=doc_repo,
    )
    consumer.run()
