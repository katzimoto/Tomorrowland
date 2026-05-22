"""Integration tests for /documents/{doc_id}/user-tags endpoints."""

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


def _setup_users(engine: Engine) -> tuple[str, str, str]:
    """Create admin, user, other. Return their emails."""
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
    return "admin@example.com", "user@example.com", "other@example.com"


def _create_doc(engine: Engine, group: str = "users") -> str:
    """Create a document accessible to *group*. Return doc_id str."""
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group)
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


# ---------------------------------------------------------------------------
# GET /documents/{doc_id}/user-tags
# ---------------------------------------------------------------------------


def test_list_tags_empty(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"/documents/{doc_id}/user-tags", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["tags"] == []


def test_list_tags_requires_auth(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    resp = client.get(f"/documents/{doc_id}/user-tags")
    assert resp.status_code == 401


def test_list_tags_no_access_returns_403_or_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    # Create doc accessible only to admins group
    doc_id = _create_doc(migrated_engine, group="admins")
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    auth = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"/documents/{doc_id}/user-tags", headers=auth)
    assert resp.status_code in (403, 404)


# ---------------------------------------------------------------------------
# POST /documents/{doc_id}/user-tags
# ---------------------------------------------------------------------------


def test_create_private_tag(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "my-tag", "visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["tag"] == "my-tag"
    assert data["visibility"] == "private"
    assert data["owned_by_me"] is True
    assert "id" in data


def test_create_public_tag(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "shared-tag", "visibility": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["visibility"] == "public"


def test_private_tag_not_visible_to_other_user(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)

    owner_token = _token(client, "user@example.com")
    client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "secret", "visibility": "private"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    other_token = _token(client, "other@example.com")
    resp = client.get(
        f"/documents/{doc_id}/user-tags",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    assert all(t["tag"] != "secret" for t in resp.json()["tags"])


def test_public_tag_visible_to_other_user(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)

    owner_token = _token(client, "user@example.com")
    client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "visible", "visibility": "public"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    other_token = _token(client, "other@example.com")
    resp = client.get(
        f"/documents/{doc_id}/user-tags",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    tags = [t["tag"] for t in resp.json()["tags"]]
    assert "visible" in tags


def test_create_tag_trims_whitespace(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "  trimmed  ", "visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["tag"] == "trimmed"


def test_create_empty_tag_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "   ", "visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_tag_too_long_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "x" * 101, "visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_duplicate_tag_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "dup", "visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "dup", "visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_tags_persist_after_relist(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "persistent", "visibility": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    auth = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"/documents/{doc_id}/user-tags", headers=auth)
    assert resp.status_code == 200
    assert any(t["tag"] == "persistent" for t in resp.json()["tags"])


# ---------------------------------------------------------------------------
# DELETE /documents/{doc_id}/user-tags/{tag_id}
# ---------------------------------------------------------------------------


def test_delete_own_tag(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")

    create_resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "to-del", "visibility": "private"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    tag_id = create_resp.json()["id"]

    del_resp = client.delete(
        f"/documents/{doc_id}/user-tags/{tag_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    list_auth = {"Authorization": f"Bearer {token}"}
    list_resp = client.get(f"/documents/{doc_id}/user-tags", headers=list_auth)
    assert all(t["id"] != tag_id for t in list_resp.json()["tags"])


def test_delete_other_users_tag_returns_403(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)

    owner_token = _token(client, "user@example.com")
    create_resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "owned", "visibility": "public"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    tag_id = create_resp.json()["id"]

    other_token = _token(client, "other@example.com")
    resp = client.delete(
        f"/documents/{doc_id}/user-tags/{tag_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 403


def test_delete_nonexistent_tag_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    fake_id = str(uuid4())
    resp = client.delete(
        f"/documents/{doc_id}/user-tags/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_admin_can_delete_any_tag(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    doc_id = _create_doc(migrated_engine)
    client = _make_client(migrated_engine)

    user_token = _token(client, "user@example.com")
    create_resp = client.post(
        f"/documents/{doc_id}/user-tags",
        json={"tag": "admin-target", "visibility": "public"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    tag_id = create_resp.json()["id"]

    admin_token = _token(client, "admin@example.com")
    resp = client.delete(
        f"/documents/{doc_id}/user-tags/{tag_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204
