"""Base class for all RabbitMQ stage consumers."""

from __future__ import annotations

import json
import logging
import signal
import threading
from abc import ABC, abstractmethod
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from uuid import UUID

import pika
import pika.adapters.blocking_connection
import pika.spec

from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient

logger = logging.getLogger(__name__)


class BaseConsumer(ABC):
    """Consume one RabbitMQ queue; ack on success, nack (→ DLQ) on failure.

    Subclasses must set:
        queue_name: str    — RabbitMQ queue to consume
        worker_type: str   — label used in logs and metrics

    Subclasses must implement:
        handle_message(job_id, document_id, source_id, attempt, correlation_id)
    """

    queue_name: str
    worker_type: str

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        health_port: int = 8080,
    ) -> None:
        self._rabbit = rabbit
        self._job_repo = job_repo
        self._health_port = health_port
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None
        self._jobs_processed: int = 0
        self._stopping = False

    @abstractmethod
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
        """Process one message. Raise on failure."""

    def run(self) -> None:
        """Connect, declare topology, consume. Blocks until SIGTERM."""
        self._rabbit.connect()
        self._rabbit.declare_topology()
        self._channel = self._rabbit._channel
        assert self._channel is not None
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._on_message,
            auto_ack=False,
        )
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)
        self._start_health_server()
        logger.info("worker started: worker_type=%s queue=%s", self.worker_type, self.queue_name)
        self._channel.start_consuming()
        logger.info("worker stopped: worker_type=%s", self.worker_type)

    def _on_message(
        self,
        channel: Any,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        delivery_tag = method.delivery_tag
        try:
            payload = json.loads(body)
            job_id = UUID(payload["job_id"])
            document_id = UUID(payload["document_id"])
            source_id = UUID(payload["source_id"])
            attempt: int = int(payload.get("attempt", 1))
            correlation_id: str = payload.get("correlation_id", "")
            content_text: str = str(payload.get("content_text", ""))
            translated_text: str = str(payload.get("translated_text", ""))
        except (KeyError, ValueError) as exc:
            logger.error(
                "malformed message: worker_type=%s error=%s body=%.200s",
                self.worker_type,
                exc,
                body,
            )
            self._channel.basic_nack(delivery_tag=delivery_tag, requeue=False)  # type: ignore[union-attr]
            return

        try:
            self.handle_message(
                job_id,
                document_id,
                source_id,
                attempt,
                correlation_id,
                content_text=content_text,
                translated_text=translated_text,
            )
            self._job_repo.commit()
            self._channel.basic_ack(delivery_tag=delivery_tag)  # type: ignore[union-attr]
            self._jobs_processed += 1
            logger.info(
                "job succeeded: worker_type=%s job_id=%s attempt=%d",
                self.worker_type,
                job_id,
                attempt,
            )
        except Exception as exc:
            max_attempts = self._job_repo.get_max_attempts(job_id)
            retry_limit = min(3, max_attempts or 5)
            if attempt < retry_limit:
                self._job_repo.mark_retry(job_id, exc, stage=self.worker_type)
                logger.warning(
                    "job retry: worker_type=%s job_id=%s attempt=%d error=%s",
                    self.worker_type,
                    job_id,
                    attempt,
                    exc,
                )
                self._channel.basic_nack(delivery_tag=delivery_tag, requeue=False)  # type: ignore[union-attr]
            elif attempt < (max_attempts or 5):
                self._job_repo.mark_retry(job_id, exc, stage=self.worker_type)
                retry_body = json.dumps(
                    {
                        "job_id": str(job_id),
                        "document_id": str(document_id),
                        "source_id": str(source_id),
                        "attempt": attempt + 1,
                        "pipeline_version": "v1",
                    }
                ).encode()
                self._channel.basic_publish(  # type: ignore[union-attr]
                    exchange="tomorrowland.documents.retry",
                    routing_key=self.queue_name,
                    body=retry_body,
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                self._channel.basic_ack(delivery_tag=delivery_tag)  # type: ignore[union-attr]
                logger.info(
                    "job routed to retry: worker_type=%s job_id=%s attempt=%d",
                    self.worker_type,
                    job_id,
                    attempt,
                )
            else:
                self._job_repo.mark_dead_letter(job_id, exc)
                logger.error(
                    "job dead-lettered: worker_type=%s job_id=%s attempt=%d error=%s",
                    self.worker_type,
                    job_id,
                    attempt,
                    exc,
                )
                self._channel.basic_nack(delivery_tag=delivery_tag, requeue=False)  # type: ignore[union-attr]

    def _handle_sigterm(self, signum: int, frame: Any) -> None:
        logger.info("shutting down: worker_type=%s", self.worker_type)
        self._stopping = True
        if self._channel and self._channel.is_open:
            self._channel.stop_consuming()

    def _start_health_server(self) -> None:
        worker_type = self.worker_type
        queue_name = self.queue_name
        consumer_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/health":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                body = json.dumps(
                    {
                        "status": "ok",
                        "worker_type": worker_type,
                        "queue": queue_name,
                        "jobs_processed": consumer_ref._jobs_processed,
                    }
                ).encode()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                pass

        server = HTTPServer(("", self._health_port), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
