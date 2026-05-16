"""Integration tests for the RAG Q&A API."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.search.hybrid import SearchResult
from services.search.qdrant import QdrantSearchClient
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def _settings(**overrides: object) -> Settings:
    return Settings(
        app_env="test",
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        **overrides,
    )


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    return str(login.json()["access_token"])


def _setup_users(engine: Engine) -> None:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )


def _create_doc(
    engine: Engine,
    group_name: str,
    doc_title: str = "RAG Test Doc",
) -> UUID:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("RAG Source")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/test.txt",
            source="folder",
            mime_type="text/plain",
            title=doc_title,
            path="/data/test.txt",
        )
        assert doc is not None
        return doc.id


def test_qa_returns_answer_and_citations(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    doc_id = _create_doc(migrated_engine, "admins", "Procurement Policy")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(
            doc_id=str(doc_id),
            score=0.92,
            chunk_text="All procurement over $10,000 requires two quotes.",
        )
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    resp = client.post(
        "/qa",
        json={"question": "What is the procurement threshold?", "top_k": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["question"] == "What is the procurement threshold?"
    assert "answer" in data
    assert len(data["citations"]) == 1
    assert data["citations"][0]["doc_id"] == str(doc_id)
    assert data["citations"][0]["doc_title"] == "Procurement Policy"
    assert "procurement" in data["citations"][0]["chunk_text"].lower()


def test_qa_no_groups_returns_empty(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    # Create a user with no groups
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="nogroup@example.com",
            password_hash=hash_password("secret"),
            display_name="No Group",
            is_admin=False,
            group_names=[],
        )

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(),
        )
    )
    login = client.post("/auth/login", json={"email": "nogroup@example.com", "password": "secret"})
    assert login.status_code == 200
    token = str(login.json()["access_token"])

    resp = client.post(
        "/qa",
        json={"question": "Hello?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "You do not belong to any groups with document access."
    assert data["citations"] == []


def test_qa_no_chunks_found(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    resp = client.post(
        "/qa",
        json={"question": "Something impossible?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "could not find" in data["answer"].lower()
    assert data["citations"] == []


def test_qa_empty_question_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(),
        )
    )
    token = _admin_token(client)

    resp = client.post(
        "/qa",
        json={"question": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_qa_ollama_failure_returns_fallback(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    doc_id = _create_doc(migrated_engine, "admins", "Fallback Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(
            doc_id=str(doc_id),
            score=0.85,
            chunk_text="Important information here.",
        )
    ]

    mock_ollama = MagicMock()
    mock_ollama.generate.side_effect = Exception("Ollama is down")
    mock_ollama._model = "mistral"

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(),
            qdrant_client=mock_qdrant,
            ollama_client=mock_ollama,
        )
    )

    token = _admin_token(client)

    resp = client.post(
        "/qa",
        json={"question": "What?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "issue" in data["answer"].lower() or "passages" in data["answer"].lower()
    assert len(data["citations"]) == 1


def test_qa_top_k_limits_chunks(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    doc_id = _create_doc(migrated_engine, "admins", "Multi Chunk Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(
            doc_id=str(doc_id),
            score=0.95,
            chunk_text=f"Chunk {i}",
        )
        for i in range(10)
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    resp = client.post(
        "/qa",
        json={"question": "Show me chunks", "top_k": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # Qdrant is called with limit=3
    mock_qdrant.search.assert_called_once()
    assert mock_qdrant.search.call_args.kwargs["limit"] == 3


def test_qa_disabled_by_settings_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_rag_qa=False),
        )
    )
    token = _admin_token(client)

    resp = client.post(
        "/qa",
        json={"question": "Can I ask this?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404


def test_qa_disabled_by_system_config_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE system_config SET value = :value WHERE key = 'feature.rag_qa'"),
            {"value": "false"},
        )

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(),
        )
    )
    token = _admin_token(client)

    resp = client.post(
        "/qa",
        json={"question": "Can I ask this?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404
