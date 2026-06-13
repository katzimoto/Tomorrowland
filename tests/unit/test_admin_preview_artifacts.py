"""Unit tests for admin preview artifact orphan cleanup endpoints (#749).

GET  /admin/preview/artifacts/orphans  — dry-run
POST /admin/preview/artifacts/sweep    — execute
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.preview.artifact_repository import PreviewArtifactRepository
from services.preview.artifact_store import PreviewArtifactStore
from shared.config import Settings


def _settings(files_root: Path, **overrides) -> Settings:
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        files_root=files_root,
        **overrides,
    )


def _create_admin(engine: Engine) -> str:
    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
    return "admin@example.com"


def _get_token(client: TestClient, email: str, password: str = "secret") -> str:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _create_regular_user(engine: Engine) -> str:
    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=[],
        )
    return "user@example.com"


# ---------------------------------------------------------------------------
# GET /admin/preview/artifacts/orphans
# ---------------------------------------------------------------------------


def test_orphans_scan_empty_root(migrated_engine: Engine, tmp_path: Path) -> None:
    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    _create_admin(migrated_engine)
    token = _get_token(client, "admin@example.com")
    resp = client.get(
        "/admin/preview/artifacts/orphans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["scanned"] == 0
    assert data["orphaned"] == 0
    assert data["deleted"] == 0
    assert data["bytes_reclaimable"] == 0


def test_orphans_scan_reports_stale_without_deleting(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    store.write_artifacts(doc_id, "stalesha", {"a": ("f.txt", "text/plain", b"stale")})

    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    _create_admin(migrated_engine)
    token = _get_token(client, "admin@example.com")
    resp = client.get(
        "/admin/preview/artifacts/orphans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["scanned"] == 1
    assert data["orphaned"] == 1
    assert data["deleted"] == 0
    # File still present after dry-run scan.
    assert store.resolve(doc_id, "stalesha", "f.txt") is not None


def test_orphans_scan_active_artifacts_not_reported(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    store.write_artifacts(doc_id, "activesha", {"a": ("f.txt", "text/plain", b"live")})
    with migrated_engine.begin() as conn:
        repo = PreviewArtifactRepository(conn)
        repo.create_pending(doc_id, "activesha", renderer="pdfjs")

    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    _create_admin(migrated_engine)
    token = _get_token(client, "admin@example.com")
    resp = client.get(
        "/admin/preview/artifacts/orphans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["orphaned"] == 0
    assert data["valid"] == 1


def test_orphans_scan_requires_admin(migrated_engine: Engine, tmp_path: Path) -> None:
    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    # Need to create admin first to be able to create the non-admin user.
    _create_admin(migrated_engine)
    _create_regular_user(migrated_engine)
    token = _get_token(client, "user@example.com")
    resp = client.get(
        "/admin/preview/artifacts/orphans",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /admin/preview/artifacts/sweep
# ---------------------------------------------------------------------------


def test_sweep_deletes_stale_artifacts(migrated_engine: Engine, tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    store.write_artifacts(doc_id, "stalesha", {"a": ("f.txt", "text/plain", b"gone")})

    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    _create_admin(migrated_engine)
    token = _get_token(client, "admin@example.com")
    resp = client.post(
        "/admin/preview/artifacts/sweep",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is False
    assert data["deleted"] == 1
    assert data["orphaned"] == 1
    assert data["error_count"] == 0
    assert data["bytes_reclaimed"] == len(b"gone")
    # File must be gone after execute.
    assert store.resolve(doc_id, "stalesha", "f.txt") is None


def test_sweep_preserves_active_artifacts(migrated_engine: Engine, tmp_path: Path) -> None:
    store = PreviewArtifactStore(tmp_path)
    doc_id = uuid4()
    store.write_artifacts(doc_id, "activesha", {"a": ("f.txt", "text/plain", b"keep")})
    with migrated_engine.begin() as conn:
        repo = PreviewArtifactRepository(conn)
        repo.create_pending(doc_id, "activesha", renderer="pdfjs")

    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    _create_admin(migrated_engine)
    token = _get_token(client, "admin@example.com")
    resp = client.post(
        "/admin/preview/artifacts/sweep",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 0
    assert data["valid"] == 1
    # Active artifact directory still present.
    assert store.resolve(doc_id, "activesha", "f.txt") is not None


def test_sweep_noop_on_empty_root(migrated_engine: Engine, tmp_path: Path) -> None:
    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    _create_admin(migrated_engine)
    token = _get_token(client, "admin@example.com")
    resp = client.post(
        "/admin/preview/artifacts/sweep",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scanned"] == 0
    assert data["deleted"] == 0
    assert data["error_count"] == 0


def test_sweep_requires_admin(migrated_engine: Engine, tmp_path: Path) -> None:
    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    _create_admin(migrated_engine)
    _create_regular_user(migrated_engine)
    token = _get_token(client, "user@example.com")
    resp = client.post(
        "/admin/preview/artifacts/sweep",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_sweep_unauthenticated_rejected(migrated_engine: Engine, tmp_path: Path) -> None:
    client = TestClient(create_app(migrated_engine, _settings(tmp_path)))
    resp = client.post("/admin/preview/artifacts/sweep")
    assert resp.status_code == 401
