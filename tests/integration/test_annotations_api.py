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

    document_id = _create_doc(migrated_engine, "admins")

    resp = client.get(
        f"/documents/{document_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == str(document_id)
    assert data["annotations"] == []


def test_create_and_list_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    document_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{document_id}/annotations",
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
        f"/documents/{document_id}/annotations",
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

    document_id = _create_doc(migrated_engine, "admins")

    # Admin creates a private annotation
    resp = client.post(
        f"/documents/{document_id}/annotations",
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
        f"/documents/{document_id}/annotations",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 0


def test_update_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    document_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{document_id}/annotations",
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

    document_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{document_id}/annotations",
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
        f"/documents/{document_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 0


def test_cannot_modify_others_annotation(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    document_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{document_id}/annotations",
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

    document_id = _create_doc(migrated_engine, "admins")

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
        f"/documents/{document_id}/annotations",
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
        f"/documents/{document_id}/annotations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 0


def test_admin_can_see_all_annotations(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    document_id = _create_doc(migrated_engine, "admins")

    # Admin creates a private annotation
    resp = client.post(
        f"/documents/{document_id}/annotations",
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
        f"/documents/{document_id}/annotations",
        json={"text": "Other private", "is_private": True},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 201

    # Admin should see both private annotations
    resp = client.get(
        f"/documents/{document_id}/annotations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["annotations"]) == 2


def test_empty_text_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    document_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{document_id}/annotations",
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
    document_id = _create_doc(migrated_engine, "admins")

    # Log in as regular user in "users" group
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    user_token = str(login.json()["access_token"])

    resp = client.post(
        f"/documents/{document_id}/annotations",
        json={"text": "Should fail"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_position_roundtrip(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    document_id = _create_doc(migrated_engine, "admins")

    position = {"page": 3, "start_char": 42, "end_char": 99}
    resp = client.post(
        f"/documents/{document_id}/annotations",
        json={"text": "Passage", "position": position},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["position"] == position


def _make_non_admin_token(
    engine: Engine,
    app: object,
    email: str,
    group_name: str = "admins",
) -> str:
    """Create a non-admin user and return a JWT for them."""

    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        auth_repo.create_local_user(
            email=email,
            password_hash=hash_password("secret"),
            display_name=email.split("@")[0],
            is_admin=False,
            group_names=[group_name],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": email},
            )
            .mappings()
            .first()
        )
    assert row is not None
    user_id = UUID(str(row["id"]))

    from services.auth.jwt import JwtService
    from services.auth.models import UserIdentity

    jwt = JwtService(secret=app.state.settings.jwt_secret)  # type: ignore[attr-defined]
    identity = UserIdentity(
        id=user_id,
        email=email,
        display_name=email.split("@")[0],
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    return jwt.encode(identity)


def test_owner_gets_can_modify_true_on_create(migrated_engine: Engine) -> None:
    """Annotation creator receives can_modify=true in the POST response."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "My annotation"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["can_modify"] is True


def test_owner_gets_can_modify_true_on_list(migrated_engine: Engine) -> None:
    """Owner sees can_modify=true for their own annotation in the list response."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")
    client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Owner annotation"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    annotations = resp.json()["annotations"]
    assert len(annotations) == 1
    assert annotations[0]["can_modify"] is True


def test_admin_gets_can_modify_true_on_others_annotation(migrated_engine: Engine) -> None:
    """Admin receives can_modify=true even for annotations they did not create."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    # Non-admin creates annotation
    non_admin_token = _make_non_admin_token(migrated_engine, app, "writer@example.com")
    client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Non-admin annotation"},
        headers={"Authorization": f"Bearer {non_admin_token}"},
    )

    # Admin lists and should see can_modify=True
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    annotations = resp.json()["annotations"]
    assert len(annotations) == 1
    assert annotations[0]["can_modify"] is True


def test_non_owner_gets_can_modify_false_on_list(migrated_engine: Engine) -> None:
    """Non-owner, non-admin user sees can_modify=false for annotations they did not create."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    # Admin creates a shared annotation
    client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Admin shared annotation", "is_private": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Non-admin user lists annotations; they are not the owner
    non_admin_token = _make_non_admin_token(migrated_engine, app, "reader@example.com")
    resp = client.get(
        f"/documents/{doc_id}/annotations",
        headers={"Authorization": f"Bearer {non_admin_token}"},
    )
    assert resp.status_code == 200
    annotations = resp.json()["annotations"]
    assert len(annotations) == 1
    assert annotations[0]["can_modify"] is False


def test_oversized_text_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "x" * 5001},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_oversized_note_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "valid text", "note": "x" * 2001},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_owner_gets_can_modify_true_on_update(migrated_engine: Engine) -> None:
    """Owner receives can_modify=true in the PUT response."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    create_resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Before update"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    annotation_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/annotations/{annotation_id}",
        json={"note": "Added note"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["can_modify"] is True


# ---------------------------------------------------------------------------
# Bug regression: delete_reply must enforce document-level access
# ---------------------------------------------------------------------------


def _user_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    return str(login.json()["access_token"])


def test_delete_reply_blocked_without_doc_access(migrated_engine: Engine) -> None:
    """delete_reply must reject callers who lost document-level access.

    Regression for the bug where DELETE /annotation-replies/{id} skipped
    assert_doc_access, allowing a revoked user to delete their own reply by
    knowing the reply UUID.
    """
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)

    # Create a doc that belongs to the "admins" group only — regular user has no access.
    doc_id = _create_doc(migrated_engine, "admins")

    admin_token = _admin_token(client)

    # Admin creates an annotation on the doc.
    ann_resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Admin annotation"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert ann_resp.status_code == 201
    annotation_id = ann_resp.json()["id"]

    # Admin creates a reply (so the reply is owned by admin).
    reply_resp = client.post(
        f"/annotations/{annotation_id}/replies",
        json={"body": "Admin reply"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reply_resp.status_code == 201
    reply_id = reply_resp.json()["id"]

    # Regular user (no doc access) tries to delete the reply — must be rejected.
    user_token = _user_token(client)
    del_resp = client.delete(
        f"/annotation-replies/{reply_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    # 403 from assert_doc_access (or 404 if reply lookup fails first) — either way not 204.
    assert del_resp.status_code in (403, 404)

    # Confirm the reply still exists (admin can still fetch replies).
    list_resp = client.get(
        f"/annotations/{annotation_id}/replies",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()["replies"]) == 1


# ---------------------------------------------------------------------------
# Bug regression: list_replies must hide replies on private annotations
# ---------------------------------------------------------------------------


def test_list_replies_hidden_for_private_annotation(migrated_engine: Engine) -> None:
    """list_replies must return 404 for a private annotation owned by another user.

    Regression for the bug where GET /annotations/{id}/replies only checked
    document-level access but not annotation-level visibility, allowing a
    non-owner with doc access to enumerate replies on a private annotation.
    """
    _setup_users(migrated_engine)

    # Doc shared with both groups so both users have document access.
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        users_group_id = auth_repo.ensure_group("users")
        admins_group_id = auth_repo.ensure_group("admins")
        source_id = auth_repo.create_ingestion_source("Shared Source")
        auth_repo.grant_source_to_group(source_id, users_group_id)
        auth_repo.grant_source_to_group(source_id, admins_group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/private-ann-test.txt",
            source="folder",
            mime_type="text/plain",
            title="Private Annotation Test Doc",
            path="/data/private-ann-test.txt",
        )
        assert doc is not None
        doc_id = doc.id

    app = create_app(migrated_engine)
    client = TestClient(app)

    admin_token = _admin_token(client)
    user_token = _user_token(client)

    # Admin creates a *private* annotation on the shared doc.
    ann_resp = client.post(
        f"/documents/{doc_id}/annotations",
        json={"text": "Private annotation", "is_private": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert ann_resp.status_code == 201
    annotation_id = ann_resp.json()["id"]

    # Admin adds a reply to their own private annotation.
    reply_resp = client.post(
        f"/annotations/{annotation_id}/replies",
        json={"body": "Private reply"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reply_resp.status_code == 201

    # Owner (admin) can list replies.
    owner_list = client.get(
        f"/annotations/{annotation_id}/replies",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert owner_list.status_code == 200
    assert len(owner_list.json()["replies"]) == 1

    # Non-owner (user) has doc access but must NOT see replies on a private annotation.
    non_owner_list = client.get(
        f"/annotations/{annotation_id}/replies",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert non_owner_list.status_code == 404
