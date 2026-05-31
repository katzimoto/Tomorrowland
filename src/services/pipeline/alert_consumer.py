from __future__ import annotations

from typing import Any
from uuid import UUID

from services.documents.repository import DocumentRepository
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient


class AlertConsumer(BaseConsumer):
    queue_name = "document.alert.requested"
    worker_type = "alert-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        alert_matcher: Any,
        doc_repo: DocumentRepository,
        health_port: int = 8086,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._alert_matcher = alert_matcher
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
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        payload = self._job_repo.get_payload(document_id)

        # Prefer translated text when available, fall back to original
        content = translated_text or (payload.get("content_text", "") if payload else None) or ""

        # Skip empty-content documents to avoid creating zero-vector entries
        if not content.strip():
            self._job_repo.mark_running_stage(job_id, "alert_done")
            return

        self._alert_matcher.match_document(doc, content)
        self._job_repo.mark_running_stage(job_id, "alert_done")


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.alerts.repository import AlertRepository
    from services.alerts.service import AlertMatcher
    from services.documents.repository import DocumentRepository
    from services.search.factory import build_encoder
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    with engine.connect() as conn:
        rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
        job_repo = PipelineJobRepository(conn)
        doc_repo = DocumentRepository(conn)
        alert_repo = AlertRepository(conn)
        encoder = build_encoder(settings)
        matcher = AlertMatcher(alert_repo, encoder)
        consumer = AlertConsumer(rabbit, job_repo, matcher, doc_repo)
        consumer.run()
