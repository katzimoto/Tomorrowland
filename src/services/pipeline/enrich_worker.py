"""Enrich stage consumer — high-quality translation for frequently viewed documents."""
from __future__ import annotations

from uuid import UUID

from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.translation.client import LibreTranslateClient


class EnrichConsumer(BaseConsumer):
    queue_name = "document.enrich.requested"
    worker_type = "enrich-worker"

    def __init__(
        self,
        rabbit,
        job_repo: PipelineJobRepository,
        translator: LibreTranslateClient,
        health_port: int = 8087,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
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
            return

        lang = payload.get("source_language") if payload else None
        if lang == "":
            lang = None
        translated = (
            self._translator.translate(content_text, source_lang=lang, target_lang="en")
            or content_text
        )
        self._job_repo.update_translated_text(document_id, translated)
        self._job_repo.mark_running_stage(job_id, "enriched")


def main() -> None:
    import logging

    import sqlalchemy as sa

    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    with engine.connect() as conn:
        rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
        job_repo = PipelineJobRepository(conn)
        translator = LibreTranslateClient(base_url=settings.libretranslate_url)
        consumer = EnrichConsumer(rabbit, job_repo, translator)
        consumer.run()
