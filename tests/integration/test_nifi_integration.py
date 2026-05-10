"""Deterministic integration-style tests for NiFi event ingestion."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import Engine

from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.permissions.enforcer import assert_doc_access
from services.pipeline.kafka_consumer import NiFiKafkaDrain


class _Message:
    def __init__(self, value: str) -> None:
        self._value = value

    def value(self) -> str:
        return self._value


class _Consumer:
    def __init__(self, message: _Message) -> None:
        self.message: _Message | None = message
        self.committed = False

    def poll(self, timeout: float) -> _Message | None:
        del timeout
        message = self.message
        self.message = None
        return message

    def commit(self, message: _Message) -> None:
        del message
        self.committed = True


def _event(source_id: UUID) -> str:
    return f"""
    {{
      "source_id": "{source_id}",
      "external_id": "flow-file-permission",
      "title": "Permission test",
      "mime_type": "text/plain",
      "source_language": "en",
      "payload": {{"type": "inline_text", "text": "permission body"}}
    }}
    """


def test_nifi_documents_preserve_source_grant_permissions(migrated_engine: Engine) -> None:
    source_id = uuid4()
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        allowed = repository.create_local_user(
            email="allowed@example.com",
            password_hash=hash_password("secret"),
            group_names=["allowed"],
        )
        denied = repository.create_local_user(
            email="denied@example.com",
            password_hash=hash_password("secret"),
            group_names=["denied"],
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, source_language)
                VALUES (:id, 'NiFi Permission Source', 'nifi', 'en')
                """
            ),
            {"id": source_id.hex},
        )
        repository.grant_source_to_group(source_id, allowed.groups[0])

    processed: list[UUID] = []
    message = _Message(_event(source_id))
    consumer = _Consumer(message)
    result = NiFiKafkaDrain(
        consumer=consumer,
        engine=migrated_engine,
        process_document=lambda doc_id, text: processed.append(doc_id),
        sleep=lambda seconds: None,
    ).drain(max_messages=1)

    assert result["processed"] == 1
    assert consumer.committed is True
    doc_id = processed[0]

    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        assert_doc_access(doc_id, allowed, repository)
        with pytest.raises(HTTPException) as exc_info:
            assert_doc_access(doc_id, denied, repository)

    assert exc_info.value.status_code == 403
