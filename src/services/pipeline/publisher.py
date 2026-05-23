"""DocumentPublisher — writes DB state and publishes RabbitMQ messages per pipeline stage."""

from __future__ import annotations

import logging
from uuid import UUID

from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient

logger = logging.getLogger(__name__)

_ROUTING_KEYS: dict[str, str] = {
    "parse": "document.parse.requested",
    "translate": "document.translate.requested",
    "embed": "document.embed.requested",
    "index": "document.index.requested",
    "intelligence": "document.intelligence.requested",
    "alert": "document.alert.requested",
    "enrich": "document.enrich.requested",
}


class DocumentPublisher:
    """Publish a document to the next pipeline stage queue.

    Always writes a DB row first; only publishes to RabbitMQ when the client
    is enabled. This means the DB-poll workers still function when
    RABBITMQ_ENABLED=false.
    """

    def __init__(
        self,
        job_repo: PipelineJobRepository,
        rabbit: RabbitClient,
    ) -> None:
        self._job_repo = job_repo
        self._rabbit = rabbit

    def publish_parse(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
        content_text: str | None = None,
    ) -> None:
        self._publish(
            "parse",
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            extra={"content_text": content_text} if content_text else {},
        )

    def publish_translate(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
    ) -> None:
        self._publish(
            "translate",
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )

    def publish_embed(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
    ) -> None:
        self._publish(
            "embed",
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )

    def publish_index(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
    ) -> None:
        self._publish(
            "index",
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )

    def publish_intelligence(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
    ) -> None:
        self._publish(
            "intelligence",
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )

    def publish_alert(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
    ) -> None:
        self._publish(
            "alert",
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )

    def publish_enrich(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
    ) -> None:
        self._publish(
            "enrich",
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
        )

    def _publish(
        self,
        stage: str,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        extra: dict[str, str] | None = None,
    ) -> None:
        routing_key = _ROUTING_KEYS[stage]
        body: dict[str, str | int] = {
            "job_id": str(job_id),
            "document_id": str(document_id),
            "source_id": str(source_id),
            "attempt": attempt,
            "pipeline_version": "v1",
        }
        if extra:
            body.update(extra)
        message_id = self._rabbit.publish(routing_key, body)
        if message_id:
            self._job_repo.set_rabbit_message_id(job_id, message_id)
        logger.info(
            "published stage=%s job_id=%s message_id=%s",
            stage,
            job_id,
            message_id or "disabled",
        )
