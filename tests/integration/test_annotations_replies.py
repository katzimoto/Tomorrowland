"""Integration tests for annotation reply endpoints."""

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


def _settings() -> Settings:
    return Settings(
        app_env="test",
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
    )


def _make_client(engine: Engine) -> TestClient:
    return TestClient(create_app(engine, _settings()))


def _token(client: TestClient, email: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": "secret"})
    assert resp.status_code == 200
    return str(resp.json()["access_token"])


def _setup_users(engine: Engine) -> tuple[str, str]:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
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
    return "user@example.com", "other@example.com"


def _create_doc(engine: Engine) -> str:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("users")
        source_id = auth_repo.create_ingestion_source(f"src-{uuid4().hex[:6]}")
        auth_repo.grant_source_to_group(source_id, group_id)
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file-{uuid4().hex}",
            source="folder",
            mime_type="text/plain",
            title="Test Doc",
        )
        assert doc is not None
        return str(doc.id)


def _create_annotation(client: TestClient, doc_id: str, token: str) -> str:
    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "test annotation", "is_private": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# GET /annotations/{id}/replies
# ---------------------------------------------------------------------------


def test_list_replies_empty(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    anno_id = _create_annotation(client, doc_id, token)
    resp = client.get(
        f"/annotations/{anno_id}/replies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["replies"] == []


def test_list_replies_requires_auth(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    anno_id = _create_annotation(client, doc_id, token)
    resp = client.get(f"/annotations/{anno_id}/replies")
    assert resp.status_code == 401


def test_list_replies_404_for_missing_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.get(
        f"/annotations/{uuid4()}/replies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /annotations/{id}/replies
# ---------------------------------------------------------------------------


def test_create_reply(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    anno_id = _create_annotation(client, doc_id, token)
    resp = client.post(
        f"/annotations/{anno_id}/replies",
        json={"body": "nice idea"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "nice idea"
    assert data["can_modify"] is True
    assert "id" in data


def test_create_reply_empty_body_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    anno_id = _create_annotation(client, doc_id, token)
    resp = client.post(
        f"/annotations/{anno_id}/replies",
        json={"body": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_reply_appears_in_reply_count(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    anno_id = _create_annotation(client, doc_id, token)
    client.post(
        f"/annotations/{anno_id}/replies",
        json={"body": "r1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/annotations/{anno_id}/replies",
        json={"body": "r2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    counter = [a for a in resp.json()["annotations"] if a["id"] == anno_id]
    assert len(counter) == 1
    assert counter[0]["reply_count"] == 2


# ---------------------------------------------------------------------------
# DELETE /annotation-replies/{id}
# ---------------------------------------------------------------------------


def test_delete_own_reply(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    anno_id = _create_annotation(client, doc_id, token)
    create_resp = client.post(
        f"/annotations/{anno_id}/replies",
        json={"body": "to-delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    reply_id = create_resp.json()["id"]
    del_resp = client.delete(
        f"/annotation-replies/{reply_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204


def test_delete_other_users_reply_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    owner_token = _token(client, "user@example.com")
    anno_id = _create_annotation(client, doc_id, owner_token)
    create_resp = client.post(
        f"/annotations/{anno_id}/replies",
        json={"body": "owned reply"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    reply_id = create_resp.json()["id"]
    other_token = _token(client, "other@example.com")
    del_resp = client.delete(
        f"/annotation-replies/{reply_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert del_resp.status_code == 404


def test_annotations_list_includes_reply_count_field(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    _create_annotation(client, doc_id, token)
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    for a in resp.json()["annotations"]:
        assert "reply_count" in a
        assert isinstance(a["reply_count"], int)
