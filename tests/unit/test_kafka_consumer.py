"""Unit tests for the bounded NiFi Kafka drain."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from services.pipeline.kafka_consumer import NiFiKafkaDrain, TransientKafkaError


class _Message:
    def __init__(self, value: bytes | str | None) -> None:
        self._value = value

    def value(self) -> bytes | str | None:
        return self._value


class _Consumer:
    def __init__(self, messages: list[_Message] | None = None, failures: int = 0) -> None:
        self.messages = messages or []
        self.failures = failures
        self.committed: list[_Message] = []

    def poll(self, timeout: float) -> _Message | None:
        del timeout
        if self.failures:
            self.failures -= 1
            raise TransientKafkaError("temporary broker outage")
        return self.messages.pop(0) if self.messages else None

    def commit(self, message: _Message) -> None:
        self.committed.append(message)


class _Dlq:
    def __init__(self, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.calls: list[dict[str, object]] = []

    def route(self, **kwargs: object) -> bool:
        self.calls.append(kwargs)
        return self.succeeds


def _insert_source(engine: Engine, *, enabled: bool = True, source_key: str = "nifi-flow") -> UUID:
    source_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, enabled, config, source_language)
                VALUES (:id, 'NiFi Flow', 'nifi', :enabled, :config, 'en')
                """
            ),
            {
                "id": source_id.hex,
                "enabled": enabled,
                "config": f'{{"source_key":"{source_key}"}}',
            },
        )
    return source_id


def _event(
    source_id: UUID | None = None,
    source_key: str | None = None,
    text: str = "hello",
) -> str:
    source_fields = (
        {"source_id": str(source_id)} if source_id is not None else {"source_key": source_key}
    )
    return str(
        {
            **source_fields,
            "external_id": "flow-file-1",
            "title": "Report",
            "mime_type": "text/plain",
            "source_language": "en",
            "payload": {"type": "inline_text", "text": text},
        }
    ).replace("'", '"')


def _drain(
    engine: Engine,
    consumer: _Consumer,
    process_document: Callable[[UUID, str | None], None] | None = None,
    dlq: _Dlq | None = None,
) -> NiFiKafkaDrain:
    return NiFiKafkaDrain(
        consumer=consumer,
        engine=engine,
        process_document=process_document or (lambda doc_id, text: None),
        dlq=dlq,
        sleep=lambda seconds: None,
    )


def test_kafka_drain_processes_inline_event_and_commits_after_pipeline(
    migrated_engine: Engine,
) -> None:
    source_id = _insert_source(migrated_engine)
    message = _Message(_event(source_id))
    consumer = _Consumer([message])
    processed: list[tuple[UUID, str | None]] = []

    result = _drain(
        migrated_engine,
        consumer,
        lambda doc_id, text: processed.append((doc_id, text)),
    ).drain(max_messages=1)

    assert result["processed"] == 1
    assert processed[0][1] == "hello"
    assert consumer.committed == [message]
    with migrated_engine.connect() as connection:
        row = connection.execute(sa.text("SELECT source, source_id FROM documents")).first()
    assert row is not None
    assert row[0] == "nifi"
    assert UUID(str(row[1])) == source_id


def test_kafka_drain_routes_malformed_event_to_dlq_and_commits(migrated_engine: Engine) -> None:
    message = _Message(b"not-json")
    consumer = _Consumer([message])
    dlq = _Dlq()

    result = _drain(migrated_engine, consumer, dlq=dlq).drain(max_messages=1)

    assert result["dlq"] == 1
    assert len(dlq.calls) == 1
    assert consumer.committed == [message]


def test_kafka_drain_routes_unknown_source_to_dlq(migrated_engine: Engine) -> None:
    message = _Message(_event(uuid4()))
    consumer = _Consumer([message])
    dlq = _Dlq()

    result = _drain(migrated_engine, consumer, dlq=dlq).drain(max_messages=1)

    assert result["dlq"] == 1
    assert "unknown_nifi_source" in str(dlq.calls[0]["reason"])
    assert consumer.committed == [message]


def test_kafka_drain_resolves_source_key(migrated_engine: Engine) -> None:
    _insert_source(migrated_engine, source_key="finance-flow")
    message = _Message(_event(source_id=None, source_key="finance-flow"))
    consumer = _Consumer([message])
    processed: list[tuple[UUID, str | None]] = []

    result = _drain(
        migrated_engine,
        consumer,
        lambda doc_id, text: processed.append((doc_id, text)),
    ).drain(max_messages=1)

    assert result["processed"] == 1
    assert processed[0][1] == "hello"
    assert consumer.committed == [message]


def test_kafka_drain_does_not_commit_when_dlq_routing_fails(migrated_engine: Engine) -> None:
    message = _Message(b"not-json")
    consumer = _Consumer([message])

    with pytest.raises(RuntimeError, match="DLQ routing failed"):
        _drain(migrated_engine, consumer, dlq=_Dlq(succeeds=False)).drain(max_messages=1)

    assert consumer.committed == []


def test_kafka_drain_routes_pipeline_failure_to_dlq_and_commits(migrated_engine: Engine) -> None:
    source_id = _insert_source(migrated_engine)
    message = _Message(_event(source_id))
    consumer = _Consumer([message])
    dlq = _Dlq()

    def fail_pipeline(doc_id: UUID, text: str | None) -> None:
        del doc_id, text
        raise RuntimeError("raw backend details must not leak")

    result = _drain(migrated_engine, consumer, fail_pipeline, dlq).drain(max_messages=1)

    assert result["dlq"] == 1
    assert dlq.calls[0]["reason"] == "pipeline_or_connector_failure"
    assert consumer.committed == [message]


def test_kafka_drain_retries_transient_consumer_errors(migrated_engine: Engine) -> None:
    source_id = _insert_source(migrated_engine)
    message = _Message(_event(source_id))
    consumer = _Consumer([message], failures=2)

    result = _drain(migrated_engine, consumer).drain(max_messages=1)

    assert result["retryable_errors"] == 2
    assert result["processed"] == 1
    assert consumer.committed == [message]


def test_kafka_drain_is_idempotent_for_source_external_id(migrated_engine: Engine) -> None:
    source_id = _insert_source(migrated_engine)
    first = _Message(_event(source_id))
    second = _Message(_event(source_id))
    consumer = _Consumer([first, second])
    processed: list[tuple[UUID, str | None]] = []

    result = _drain(
        migrated_engine,
        consumer,
        lambda doc_id, text: processed.append((doc_id, text)),
    ).drain(max_messages=2)

    assert result["processed"] == 2
    assert len(processed) == 1
    assert consumer.committed == [first, second]
