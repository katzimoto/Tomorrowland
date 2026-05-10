"""Bounded Kafka drain for NiFi event ingestion."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine, RowMapping
from sqlalchemy.exc import IntegrityError

from services.connectors.base import ConnectorDocument
from services.connectors.nifi import (
    NiFiConnector,
    NiFiEventEnvelope,
    NiFiEventError,
    parse_nifi_event,
)
from services.documents.repository import DocumentRepository
from shared.db import db_uuid, to_uuid

logger = logging.getLogger(__name__)

DLQReason = str


class KafkaMessage(Protocol):
    """Small protocol satisfied by confluent-kafka messages and unit-test fakes."""

    def value(self) -> bytes | str | None:
        """Return the message payload."""
        ...


class KafkaConsumer(Protocol):
    """Minimal consumer protocol used by the bounded drain."""

    def poll(self, timeout: float) -> KafkaMessage | None:
        """Return the next message or None on timeout."""
        ...

    def commit(self, message: KafkaMessage) -> None:
        """Commit the offset for a successfully handled message."""
        ...


class DeadLetterSink(Protocol):
    """Protocol for durable DLQ routing."""

    def route(
        self,
        *,
        reason: DLQReason,
        event: NiFiEventEnvelope | None,
        doc_id: UUID | None,
    ) -> bool:
        """Persist a terminal failure and return True only when durable."""
        ...


class TransientKafkaError(RuntimeError):
    """Raised by fake or concrete consumers for retryable infrastructure failures."""


class DatabaseDeadLetterSink:
    """Store sanitized NiFi/Kafka failures in Neverland's DLQ table."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def route(
        self,
        *,
        reason: DLQReason,
        event: NiFiEventEnvelope | None,
        doc_id: UUID | None,
    ) -> bool:
        """Insert a sanitized DLQ row without raw payload, secrets, paths, or backend details."""
        error_message = _safe_dlq_message(reason, event)
        with self._engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO dlq (id, doc_id, error_message, status)
                    VALUES (:id, :doc_id, :error_message, 'pending')
                    """
                ),
                {
                    "id": db_uuid(uuid4()),
                    "doc_id": db_uuid(doc_id) if doc_id is not None else None,
                    "error_message": error_message,
                },
            )
        return True


class NiFiKafkaDrain:
    """Drain a bounded number of Kafka records into the standard document pipeline."""

    def __init__(
        self,
        *,
        consumer: KafkaConsumer,
        engine: Engine,
        process_document: Callable[[UUID, str | None], None],
        dlq: DeadLetterSink | None = None,
        poll_timeout: float = 1.0,
        max_backoff_seconds: float = 8.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._consumer = consumer
        self._engine = engine
        self._process_document = process_document
        self._dlq = dlq or DatabaseDeadLetterSink(engine)
        self._poll_timeout = poll_timeout
        self._max_backoff_seconds = max_backoff_seconds
        self._sleep = sleep

    def drain(self, *, max_messages: int) -> dict[str, int]:
        """Poll and handle at most *max_messages* messages, then return outcome counts."""
        outcomes = {"processed": 0, "dlq": 0, "empty": 0, "retryable_errors": 0}
        backoff = 0.25
        handled = 0
        while handled < max_messages:
            try:
                message = self._consumer.poll(self._poll_timeout)
            except TransientKafkaError:
                outcomes["retryable_errors"] += 1
                self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_seconds)
                continue

            backoff = 0.25
            if message is None:
                outcomes["empty"] += 1
                break

            outcome = self._handle_message(message)
            outcomes[outcome] += 1
            handled += 1
        return outcomes

    def _handle_message(self, message: KafkaMessage) -> str:
        event: NiFiEventEnvelope | None = None
        doc_id: UUID | None = None
        try:
            value = message.value()
            if value is None:
                raise NiFiEventError("Kafka message value is empty")
            event = parse_nifi_event(value)
            source_row = self._source_row(event)
            connector = NiFiConnector(_connector_config(source_row, event))
            connector.validate()
            item = connector.normalize_event(event)
            doc_id = self._create_document(source_row, item)
            if doc_id is not None:
                self._process_document(doc_id, item.text_content)
            self._consumer.commit(message)
            return "processed"
        except NiFiEventError as exc:
            return self._route_to_dlq_or_raise(message, reason=str(exc), event=event, doc_id=doc_id)
        except (ValueError, IntegrityError) as exc:
            return self._route_to_dlq_or_raise(
                message, reason=_classified_reason(exc), event=event, doc_id=doc_id
            )
        except Exception as exc:
            return self._route_to_dlq_or_raise(
                message, reason=_classified_reason(exc), event=event, doc_id=doc_id
            )

    def _route_to_dlq_or_raise(
        self,
        message: KafkaMessage,
        *,
        reason: DLQReason,
        event: NiFiEventEnvelope | None,
        doc_id: UUID | None,
    ) -> str:
        if self._dlq.route(reason=reason, event=event, doc_id=doc_id):
            self._consumer.commit(message)
            return "dlq"
        raise RuntimeError("NiFi event DLQ routing failed")

    def _source_row(self, event: NiFiEventEnvelope) -> RowMapping:
        with self._engine.begin() as connection:
            if event.source_id is not None:
                row = (
                    connection.execute(
                        sa.text("SELECT * FROM ingestion_sources WHERE id = :id"),
                        {"id": db_uuid(event.source_id)},
                    )
                    .mappings()
                    .first()
                )
            else:
                row = _source_row_by_key(connection, event.source_key or "")
            if row is None:
                raise ValueError("unknown_nifi_source")
            if str(row["type"]) != "nifi":
                raise ValueError("source_is_not_nifi")
            if not bool(row["enabled"]):
                raise ValueError("nifi_source_disabled")
            return row

    def _create_document(self, source_row: RowMapping, item: ConnectorDocument) -> UUID | None:
        with self._engine.begin() as connection:
            existing_id = connection.execute(
                sa.text(
                    """
                    SELECT id FROM documents
                    WHERE source_id = :source_id AND external_id = :external_id
                    """
                ),
                {"source_id": source_row["id"], "external_id": item.external_id},
            ).scalar_one_or_none()
            if existing_id is not None:
                return None
            doc_repo = DocumentRepository(connection)
            document = doc_repo.create(
                source_id=to_uuid(source_row["id"]),
                external_id=item.external_id,
                source="nifi",
                mime_type=item.mime_type,
                path=item.path,
                title=item.title,
                source_language=item.source_language or source_row.get("source_language"),
                sha256=item.sha256,
                metadata=item.metadata,
            )
            return None if document is None else document.id


def _source_row_by_key(connection: Connection, source_key: str) -> RowMapping | None:
    rows = connection.execute(sa.text("SELECT * FROM ingestion_sources WHERE type = 'nifi'"))
    for row in rows.mappings():
        config = _parse_config(row.get("config"))
        if config.get("source_key") == source_key or row["name"] == source_key:
            return row
    return None


def _connector_config(source_row: RowMapping, event: NiFiEventEnvelope) -> dict[str, Any]:
    config = _parse_config(source_row.get("config"))
    config["source_id"] = str(event.source_id or to_uuid(source_row["id"]))
    if event.source_key is not None:
        config.setdefault("source_key", event.source_key)
    return config


def _parse_config(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw:
        parsed = json.loads(raw)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _safe_dlq_message(reason: DLQReason, event: NiFiEventEnvelope | None) -> str:
    parts = [f"nifi_event_failure:{_safe_token(reason)}"]
    if event is not None:
        parts.append(f"external_id={event.external_id[:128]}")
        if event.correlation_id is not None:
            parts.append(f"correlation_id={event.correlation_id[:128]}")
    return " ".join(parts)


def _safe_token(value: object) -> str:
    text = str(value).lower()
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in text)[:96]


def _classified_reason(exc: BaseException) -> str:
    text = str(exc)
    if text in {"unknown_nifi_source", "source_is_not_nifi", "nifi_source_disabled"}:
        return text
    if isinstance(exc, IntegrityError):
        return "document_persistence_failure"
    if isinstance(exc, ValueError) and text.startswith("NiFi"):
        return text
    return "pipeline_or_connector_failure"
