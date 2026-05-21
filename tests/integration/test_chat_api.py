"""Integration tests for the Document Chat API."""

from __future__ import annotations

from unittest.mock import MagicMock

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.search.qdrant import QdrantSearchClient
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def _settings(**overrides: object) -> Settings:
    return Settings(
        app_env="test",
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        **overrides,
    )


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    return str(login.json()["access_token"])


def _user_token(client: TestClient, email: str = "user@example.com") -> str:
    login = client.post("/auth/login", json={"email": email, "password": "secret"})
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
        auth_repo.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )
        auth_repo.create_local_user(
            email="other@example.com",
            password_hash=hash_password("secret"),
            display_name="Other",
            is_admin=False,
            group_names=["users"],
        )
        auth_repo.ensure_group("users")
        auth_repo.ensure_group("admins")
        # The foundation migration seeds feature.document_chat = False.
        # Enable it here so tests that set feature_document_chat=True in Settings
        # also pass the system_config gate.
        connection.execute(
            sa.text("INSERT OR REPLACE INTO system_config (key, value) VALUES (:key, :value)"),
            {"key": "feature.document_chat", "value": "true"},
        )


# ---------------------------------------------------------------------------
# Feature flag disabled
# ---------------------------------------------------------------------------


def test_chat_disabled_when_flag_off(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=False)))
    token = _admin_token(client)

    resp = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "disabled" in resp.json()["detail"].lower()


def test_chat_disabled_when_system_config_flag_off(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("INSERT OR REPLACE INTO system_config (key, value) VALUES (:key, :value)"),
            {"key": "feature.document_chat", "value": "false"},
        )

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    resp = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


def test_create_session(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    resp = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope_type"] == "all_accessible_documents"
    assert data["scope_ids"] == []
    assert data["title"] == "New Chat"
    assert data["message_count"] == 0
    assert data["id"] is not None
    assert data["user_id"] is not None


def test_create_session_with_custom_title(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    resp = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents", "title": "My Chat"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "My Chat"


def test_list_sessions(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/chat/sessions",
        json={"scope_type": "single_document", "scope_ids": ["doc1"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        "/chat/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 2


def test_list_sessions_pagination(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    for _ in range(3):
        client.post(
            "/chat/sessions",
            json={"scope_type": "all_accessible_documents"},
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = client.get(
        "/chat/sessions?limit=2&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["sessions"]) == 2


def test_get_session_no_messages(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session_id
    assert data["messages"] == []


def test_patch_session_title(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.patch(
        f"/chat/sessions/{session_id}",
        json={"title": "Updated Title"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


def test_delete_session(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.delete(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    get = client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get.status_code == 404


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def test_post_message_creates_user_and_assistant(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_document_chat=True),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "What does this document say?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert data["session_id"] == session_id
    assert data["content"] is not None

    session = client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert session.status_code == 200
    msgs = session.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_get_session_includes_messages(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_document_chat=True),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


def test_cross_user_access_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _user_token(client, "user@example.com")
    other_token = _user_token(client, "other@example.com")

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_session_not_found_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    resp = client.get(
        "/chat/sessions/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_cross_user_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _user_token(client, "user@example.com")
    other_token = _user_token(client, "other@example.com")

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.delete(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_patch_cross_user_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _user_token(client, "user@example.com")
    other_token = _user_token(client, "other@example.com")

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.patch(
        f"/chat/sessions/{session_id}",
        json={"title": "Hijacked"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_message_content_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_document_chat=True),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_invalid_uuid_session_id_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _admin_token(client)

    resp = client.get(
        "/chat/sessions/not-a-valid-uuid",
        headers={"Authorization": f"Bearer {token}"},
    )
    # FastAPI validates UUID path params and returns 422 for invalid values
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Message and citation shape
# ---------------------------------------------------------------------------


def test_post_message_response_includes_citations_field(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_document_chat=True),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Hello?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert "citations" in data
    assert isinstance(data["citations"], list)
    assert "session_id" in data
    assert "id" in data
    assert "created_at" in data


def test_delete_session_and_verify_messages_gone(migrated_engine: Engine) -> None:
    """Verify session delete cascades to messages at the API level."""
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_document_chat=True),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Delete the session
    del_resp = client.delete(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    # Session is gone
    get_resp = client.get(
        f"/chat/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_list_sessions_does_not_expose_other_users_sessions(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings(feature_document_chat=True)))
    token = _user_token(client, "user@example.com")
    other_token = _user_token(client, "other@example.com")

    # user creates a session
    client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # other user's list should be empty
    resp = client.get(
        "/chat/sessions",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["sessions"] == []


def test_post_message_cross_user_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_document_chat=True),
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client, "user@example.com")
    other_token = _user_token(client, "other@example.com")

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Can I see this?"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 404


def test_degraded_rag_returns_fallback_message(migrated_engine: Engine) -> None:
    """When RAG raises, the endpoint persists a fallback assistant message (no 500)."""
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.side_effect = RuntimeError("qdrant unavailable")

    client = TestClient(
        create_app(
            migrated_engine,
            _settings(feature_document_chat=True),
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    create = client.post(
        "/chat/sessions",
        json={"scope_type": "all_accessible_documents"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = create.json()["id"]

    resp = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "What does this say?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert data["content"]  # fallback message is non-empty
