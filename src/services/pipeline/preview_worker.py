"""Preview render stage consumer — produces preview artifacts (#539).

All artifact-writing preview renders run here, never in the API process (the
API mounts files_data read-only). Render failures are persisted as terminal
artifact states by ``render_document_preview`` and the job still succeeds;
only infrastructure errors propagate into the normal retry path.
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa

from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.preview.render import render_document_preview
from shared.config import Settings
from shared.rabbit import RabbitClient

logger = logging.getLogger(__name__)


class PreviewConsumer(BaseConsumer):
    queue_name = "document.preview.requested"
    worker_type = "preview-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        connection: sa.Connection,
        settings: Settings,
        health_port: int = 8088,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._connection = connection
        self._settings = settings

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
        self._job_repo.mark_running_stage(job_id, "preview")
        status = render_document_preview(self._connection, self._settings, document_id)
        self._job_repo.mark_succeeded(job_id)
        logger.info("preview render finished: document_id=%s status=%s", document_id, status)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    connection = engine.connect()
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
    job_repo = PipelineJobRepository(connection)
    consumer = PreviewConsumer(rabbit, job_repo, connection, settings)
    consumer.run()
