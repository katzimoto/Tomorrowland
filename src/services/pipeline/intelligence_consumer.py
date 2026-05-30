from __future__ import annotations

from typing import Any
from uuid import UUID

from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient


class IntelligenceConsumer(BaseConsumer):
    queue_name = "document.intelligence.requested"
    worker_type = "intelligence-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        intelligence_worker: Any,
        health_port: int = 8085,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._intelligence = intelligence_worker

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
        if content_text:
            self._intelligence.process_document(document_id, content_text, source_id=source_id)
        else:
            payload = self._job_repo.get_payload(document_id)
            content = (payload.get("content_text", "") if payload else None) or ""
            if content:
                self._intelligence.process_document(document_id, content, source_id=source_id)
        self._job_repo.mark_running_stage(job_id, "intelligence_done")


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.intelligence.factory import build_llm_provider
    from services.intelligence.profile_repository import ProfileRepository
    from services.intelligence.repository import IntelligenceRepository
    from services.intelligence.worker import IntelligenceWorker
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    with engine.connect() as conn:
        rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
        job_repo = PipelineJobRepository(conn)
        intelligence = IntelligenceWorker(
            repository=IntelligenceRepository(conn),
            ollama_client=build_llm_provider(settings),
            utility_model=settings.effective_utility_model,
            profile_repo=ProfileRepository(conn),
        )
        consumer = IntelligenceConsumer(rabbit, job_repo, intelligence)
        consumer.run()
