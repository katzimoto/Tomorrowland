"""Integration tests for the annotations API."""

from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.jwt import JwtService
from services.auth.models import UserIdentity
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository


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
        auth_repo.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )


def _create_doc(
    engine: Engine,
    group_name: str,
    doc_title: str = "Annotation Test Doc",
) -> UUID:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Annotation Source")
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


def test_list_annotations_empty(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == str(doc_id)
    assert data["annotations"] == []


def test_create_and_list_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Important passage", "note": "This is key", "is_private": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["text"] == "Important passage"
    assert data["note"] == "This is key"
    assert data["is_private"] is False

    # List shows it
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["annotations"]) == 1
    assert data["annotations"][0]["text"] == "Important passage"


def test_private_annotations_not_visible_to_others(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    # Admin creates a private annotation
    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Secret", "note": "Private note", "is_private": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201

    # Create another user in admins group
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="other@example.com",
            password_hash=hash_password("secret"),
            display_name="Other",
            is_admin=False,
            group_names=["admins"],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": "other@example.com"},
            )
            .mappings()
            .first()
        )
    assert row is not None
    other_id = UUID(str(row["id"]))

    jwt = JwtService(secret=app.state.settings.jwt_secret)
    other_identity = UserIdentity(
        id=other_id,
        email="other@example.com",
        display_name="Other",
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    other_token = jwt.encode(other_identity)

    # Other user should not see private annotation
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 0


def test_update_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Original text", "note": "Original note"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    annotation_id = resp.json()["id"]

    resp = client.put(
        f"/annotations/{annotation_id}",
        json={"note": "Updated note", "is_private": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["note"] == "Updated note"
    assert data["is_private"] is True
    assert data["text"] == "Original text"  # unchanged


def test_delete_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "To delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    annotation_id = resp.json()["id"]

    resp = client.delete(
        f"/annotations/{annotation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Verify list is empty
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 0


def test_cannot_modify_others_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Admin annotation"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    annotation_id = resp.json()["id"]

    # Create another user in admins group
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="user2@example.com",
            password_hash=hash_password("secret"),
            display_name="User Two",
            is_admin=False,
            group_names=["admins"],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": "user2@example.com"},
            )
            .mappings()
            .first()
        )
    assert row is not None
    user2_id = UUID(str(row["id"]))

    jwt = JwtService(secret=app.state.settings.jwt_secret)
    user2_identity = UserIdentity(
        id=user2_id,
        email="user2@example.com",
        display_name="User Two",
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    user2_token = jwt.encode(user2_identity)

    resp = client.put(
        f"/annotations/{annotation_id}",
        json={"note": "Edited by user2"},
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert resp.status_code == 403


def test_admin_can_delete_others_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    # Create a regular user in admins group
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="regular@example.com",
            password_hash=hash_password("secret"),
            display_name="Regular",
            is_admin=False,
            group_names=["admins"],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": "regular@example.com"},
            )
            .mappings()
            .first()
        )
    assert row is not None
    regular_id = UUID(str(row["id"]))

    jwt = JwtService(secret=app.state.settings.jwt_secret)
    regular_identity = UserIdentity(
        id=regular_id,
        email="regular@example.com",
        display_name="Regular",
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    regular_token = jwt.encode(regular_identity)

    # Regular user creates an annotation
    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Regular annotation"},
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert resp.status_code == 201
    annotation_id = resp.json()["id"]

    # Admin deletes it
    resp = client.delete(
        f"/annotations/{annotation_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204

    # Verify it's gone
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 0


def test_admin_can_see_all_annotations(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    # Admin creates a private annotation
    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Admin private", "is_private": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201

    # Create another user with private annotation
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="other@example.com",
            password_hash=hash_password("secret"),
            display_name="Other",
            is_admin=False,
            group_names=["admins"],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": "other@example.com"},
            )
            .mappings()
            .first()
        )
    assert row is not None
    other_id = UUID(str(row["id"]))

    jwt = JwtService(secret=app.state.settings.jwt_secret)
    other_identity = UserIdentity(
        id=other_id,
        email="other@example.com",
        display_name="Other",
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    other_token = jwt.encode(other_identity)

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Other private", "is_private": True},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 201

    # Admin should see both private annotations
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 2


def test_empty_text_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_update_nonexistent_annotation_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    resp = client.put(
        f"/annotations/{uuid4()}",
        json={"note": "Should fail"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_nonexistent_annotation_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    resp = client.delete(
        f"/annotations/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_cannot_annotate_inaccessible_doc(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)

    # Create a doc only accessible to "admins" group
    doc_id = _create_doc(migrated_engine, "admins")

    # Log in as regular user in "users" group
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    user_token = str(login.json()["access_token"])

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Should fail"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_position_roundtrip(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    position = {"page": 3, "start_char": 42, "end_char": 99}
    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Passage", "position": position},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["position"] == position
