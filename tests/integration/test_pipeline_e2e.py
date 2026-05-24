from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pika
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.search.elastic import ElasticsearchSearchClient
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.config import Settings
from tests.integration.test_pipeline import (
    TEST_JWT_SECRET,
    _admin_token,
    _create_folder_source,
    _setup_admin,
)

pytestmark = pytest.mark.e2e


def test_sync_now_publishes_to_rabbitmq(
    migrated_engine: Engine,
    rabbitmq_container: str,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    source_folder = tmp_path / "source"
    source_folder.mkdir()
    fixture_file = source_folder / "hello.txt"
    fixture_file.write_text("Hello world")
    source_id = _create_folder_source(migrated_engine, source_folder)

    settings = Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        rabbitmq_url=rabbitmq_container,
        rabbitmq_enabled=True,
    )
    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "Bonjour le monde"

    client = TestClient(
        create_app(
            migrated_engine,
            settings,
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["enqueued"] == 1
    assert body["discovered"] == 1

    params = pika.URLParameters(rabbitmq_container)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    method_frame, _, message_body = ch.basic_get(queue="document.parse.requested", auto_ack=False)
    assert method_frame is not None, "Expected a message on document.parse.requested queue"
    ch.basic_ack(method_frame.delivery_tag)
    conn.close()

    message = json.loads(message_body)
    assert "job_id" in message
    assert "document_id" in message
    assert str(source_id) == message["source_id"]
    assert message["content_text"] == "Hello world"
    assert message["pipeline_version"] == "v1"


def test_sync_now_skips_rabbitmq_when_disabled(
    migrated_engine: Engine,
    rabbitmq_container: str,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    source_folder = tmp_path / "source"
    source_folder.mkdir()
    fixture_file = source_folder / "hello.txt"
    fixture_file.write_text("Hello world")
    source_id = _create_folder_source(migrated_engine, source_folder)

    settings = Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        rabbitmq_url=rabbitmq_container,
        rabbitmq_enabled=False,
    )
    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)

    client = TestClient(
        create_app(
            migrated_engine,
            settings,
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    params = pika.URLParameters(rabbitmq_container)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    method_frame, _, _ = ch.basic_get(queue="document.parse.requested", auto_ack=False)
    assert method_frame is None, "Expected no message when rabbitmq is disabled"
    conn.close()
