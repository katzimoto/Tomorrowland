"""Integration tests for the citation feedback API."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
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


def _user_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
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
        auth_repo.ensure_group("users")
        auth_repo.ensure_group("admins")


def _create_source_with_doc(engine: Engine, group_name: str) -> tuple[str, str]:
    """Create a source, grant it to a group, and insert a document. Returns (source_id, doc_id)."""
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Test Source")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/test.txt",
            source="folder",
            mime_type="text/plain",
            title="Test Doc",
            path="/data/test.txt",
        )
        assert doc is not None
        return str(source_id), str(doc.id)


# ---------------------------------------------------------------------------
# POST /citation-feedback
# ---------------------------------------------------------------------------


def test_submit_feedback_admin_bypasses_access_check(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    # Doc in "admins" source; admin submits feedback without being a member of admins group
    _, doc_id = _create_source_with_doc(migrated_engine, "admins")

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        "/citation-feedback",
        json={"document_id": doc_id, "feedback_type": "wrong_passage"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ok"] is True
    assert "id" in data


def test_submit_feedback_user_with_access_succeeds(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users")

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    resp = client.post(
        "/citation-feedback",
        json={
            "document_id": doc_id,
            "feedback_type": "correct",
            "comment": "Great citation",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["ok"] is True


def test_submit_feedback_user_without_access_returns_403(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    # Doc belongs to "admins" source — "user" is only in "users" group
    _, doc_id = _create_source_with_doc(migrated_engine, "admins")

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    resp = client.post(
        "/citation-feedback",
        json={"document_id": doc_id, "feedback_type": "wrong_passage"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "access" in resp.json()["detail"].lower()


def test_submit_feedback_unknown_document_returns_403_for_non_admin(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    resp = client.post(
        "/citation-feedback",
        json={"document_id": str(uuid4()), "feedback_type": "other"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # source_id is None → treated as no access
    assert resp.status_code == 403


def test_submit_feedback_unauthenticated_returns_401(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings()))

    resp = client.post(
        "/citation-feedback",
        json={"document_id": str(uuid4()), "feedback_type": "other"},
    )
    assert resp.status_code == 401


def test_submit_feedback_invalid_type_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        "/citation-feedback",
        json={"document_id": str(uuid4()), "feedback_type": "not_a_valid_type"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_submit_feedback_missing_document_id_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        "/citation-feedback",
        json={"feedback_type": "correct"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_submit_feedback_persists_all_optional_fields(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "admins")

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        "/citation-feedback",
        json={
            "document_id": doc_id,
            "citation_id": "cit-xyz",
            "chunk_id": "chunk-abc",
            "feedback_type": "unsupported_claim",
            "comment": "No evidence for this claim",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    feedback_id = resp.json()["id"]

    list_resp = client.get(
        f"/citation-feedback/by-document/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == feedback_id
    assert item["citation_id"] == "cit-xyz"
    assert item["chunk_id"] == "chunk-abc"
    assert item["feedback_type"] == "unsupported_claim"
    assert item["comment"] == "No evidence for this claim"
    assert item["document_id"] == doc_id


# ---------------------------------------------------------------------------
# GET /citation-feedback/by-document/{document_id}
# ---------------------------------------------------------------------------


def test_list_by_document_admin_returns_all_items(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "admins")

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    for _ in range(3):
        client.post(
            "/citation-feedback",
            json={"document_id": doc_id, "feedback_type": "correct"},
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = client.get(
        f"/citation-feedback/by-document/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    assert all(i["document_id"] == doc_id for i in items)


def test_list_by_document_non_admin_returns_403(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    resp = client.get(
        f"/citation-feedback/by-document/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_list_by_document_empty_for_document_with_no_feedback(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        f"/citation-feedback/by-document/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_list_by_document_response_shape(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "admins")

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    client.post(
        "/citation-feedback",
        json={"document_id": doc_id, "feedback_type": "wrong_passage", "comment": "nope"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        f"/citation-feedback/by-document/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    item = resp.json()["items"][0]
    assert "id" in item
    assert "document_id" in item
    assert "feedback_type" in item
    assert "comment" in item
    assert "user_id" in item
    assert "created_at" in item
