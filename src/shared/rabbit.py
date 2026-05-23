"""Thin RabbitMQ client wrapper for Tomorrowland document pipeline."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

import pika
import pika.exceptions
from pika.spec import BasicProperties

logger = logging.getLogger(__name__)

_MAIN_EXCHANGE = "tomorrowland.documents"
_DLQ_EXCHANGE = "tomorrowland.documents.dlq"
_RETRY_EXCHANGE = "tomorrowland.documents.retry"

_STAGE_QUEUES = [
    "document.parse.requested",
    "document.translate.requested",
    "document.embed.requested",
    "document.index.requested",
    "document.intelligence.requested",
    "document.alert.requested",
    "document.enrich.requested",
]


class RabbitConnectionError(RuntimeError):
    """Raised when a connection to RabbitMQ cannot be established."""


class RabbitClient:
    """Synchronous pika-based RabbitMQ client.

    When *enabled* is False every method is a no-op so callers need no
    conditional logic — they always call connect/publish/close.
    """

    def __init__(self, url: str, *, enabled: bool = True) -> None:
        self._url = url
        self._enabled = enabled
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    def connect(self) -> None:
        """Open a connection and channel. Raises RabbitConnectionError on failure."""
        if not self._enabled:
            return
        try:
            params = pika.URLParameters(self._url)
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
        except Exception as exc:
            raise RabbitConnectionError(
                f"Cannot connect to RabbitMQ at {self._url}: {exc}"
            ) from exc

    def declare_topology(self) -> None:
        """Declare exchanges, queues, and bindings — idempotent."""
        if not self._enabled or self._channel is None:
            return
        ch = self._channel
        ch.exchange_declare(exchange=_MAIN_EXCHANGE, exchange_type="topic", durable=True)
        ch.exchange_declare(exchange=_DLQ_EXCHANGE, exchange_type="fanout", durable=True)
        ch.exchange_declare(exchange=_RETRY_EXCHANGE, exchange_type="topic", durable=True)
        for queue in _STAGE_QUEUES:
            ch.queue_declare(
                queue=queue,
                durable=True,
                arguments={"x-dead-letter-exchange": _DLQ_EXCHANGE},
            )
            ch.queue_bind(queue=queue, exchange=_MAIN_EXCHANGE, routing_key=queue)
            dlq = queue.replace("requested", "dead")
            ch.queue_declare(queue=dlq, durable=True)
            ch.queue_bind(queue=dlq, exchange=_DLQ_EXCHANGE, routing_key="#")
            retry = queue.replace("requested", "retry")
            ch.queue_declare(
                queue=retry,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": _MAIN_EXCHANGE,
                    "x-dead-letter-routing-key": queue,
                    "x-message-ttl": 30000,
                },
            )
            ch.queue_bind(queue=retry, exchange=_RETRY_EXCHANGE, routing_key=queue)

    def publish(self, routing_key: str, body: dict[str, Any]) -> str:
        """Publish a persistent JSON message. Returns the message_id UUID string."""
        if not self._enabled or self._channel is None:
            return ""
        message_id = str(uuid4())
        props = BasicProperties(
            delivery_mode=2,
            content_type="application/json",
            message_id=message_id,
        )
        self._channel.basic_publish(
            exchange=_MAIN_EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(body).encode(),
            properties=props,
        )
        logger.debug("published routing_key=%s message_id=%s", routing_key, message_id)
        return message_id

    def close(self) -> None:
        """Close the connection gracefully."""
        if not self._enabled:
            return
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            logger.debug("RabbitMQ connection already closed", exc_info=True)
