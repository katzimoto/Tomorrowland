"""Translate stage consumer — translates extracted text and publishes embed."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from services.documents.repository import DocumentRepository, TranslationVersionRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.translation.client import LibreTranslateClient

logger = logging.getLogger(__name__)


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
        health_port: int = 8082,
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
        content_text: str = "",
        translated_text: str = "",
    ) -> None:
        doc = self._doc_repo.get_by_id(document_id) if self._doc_repo else None
        lang = doc.source_language if doc else None
        if lang == "":
            lang = None
        target_lang = (doc.target_language if doc else None) or "en"

        if not content_text:
            logger.debug("translate skipped: empty content_text for document_id=%s", document_id)
            self._job_repo.mark_running_stage(job_id, "translated")
            self._publisher.publish_embed(
                job_id=job_id,
                document_id=document_id,
                source_id=source_id,
                attempt=attempt,
                content_text=content_text,
            )
            return

        translated = content_text
        if self._translator:
            translated = (
                self._translator.translate(content_text, source_lang=lang, target_lang=target_lang)
                or content_text
            )

        self._job_repo.update_translated_text(document_id, translated)
        self._job_repo.mark_running_stage(job_id, "translated")

        did_translate = translated != content_text
        quality = "fast" if did_translate else None

        if self._version_repo and did_translate:
            existing = self._version_repo.find_pending_or_running(document_id, target_lang)
            if existing is not None:
                self._version_repo.update_version_status(
                    UUID(str(existing["id"])),
                    "available",
                    translated_text=translated,
                )
            else:
                self._version_repo.create_version(
                    document_id=document_id,
                    label="Ingestion",
                    quality="fast",
                    request_type="ingestion",
                    target_language=target_lang,
                    translated_text=translated,
                )

        self._job_repo.commit()
        # Defer document indexing status to the IndexConsumer — do not call
        # update_indexed here so the document only transitions to "indexed"
        # after Meilisearch indexing has actually succeeded.
        if self._doc_repo and translated and quality is not None:
            self._doc_repo.update_translation_quality(document_id, quality)
        self._publisher.publish_index(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated,
        )
        self._publisher.publish_embed(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated,
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
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
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
