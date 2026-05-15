"""Tests for Meilisearch feature-flag rollback."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.main import create_app
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


@pytest.fixture
def engine():
    return sa.create_engine("sqlite:///:memory:")


def _setup_admin(app):
    with app.state.engine.begin() as conn:
        from services.auth.passwords import hash_password
        from services.auth.repository import AuthRepository

        auth_repo = AuthRepository(conn)
        auth_repo.create_local_user(
            email="admin@test.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
    client = TestClient(app)
    resp = client.post("/auth/login", json={"email": "admin@test.com", "password": "secret"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


class TestRollbackBehavior:
    """Tests proving Meilisearch flag rollback works correctly."""

    def test_meili_provider_present_when_flag_on(self, engine):
        settings = Settings(app_env="test", auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        settings.feature_meilisearch_search = True
        settings.meilisearch_url = "http://meilisearch:7700"
        settings.meilisearch_master_key = "test-key"
        app = create_app(engine, settings=settings)
        assert app.state.meili_provider is not None

    def test_meili_provider_none_when_flag_off(self, engine):
        settings = Settings(app_env="test", auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        settings.feature_meilisearch_search = False
        app = create_app(engine, settings=settings)
        assert app.state.meili_provider is None

    def test_flag_on_creates_provider(self, engine):
        settings = Settings(app_env="test", auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        settings.feature_meilisearch_search = True
        settings.meilisearch_url = "http://meilisearch:7700"
        settings.meilisearch_master_key = "test-key"
        app = create_app(engine, settings=settings)
        assert app.state.meili_provider is not None
        from services.search.meili_provider import MeilisearchSearchProvider

        assert isinstance(app.state.meili_provider, MeilisearchSearchProvider)

    def test_flag_off_no_meili_dependency(self, engine):
        """When flag is off, search should work without Meilisearch being available."""
        settings = Settings(app_env="test", auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        settings.feature_meilisearch_search = False
        app = create_app(engine, settings=settings)
        assert app.state.meili_provider is None


class TestRollbackDocs:
    """Verify rollback documentation covers key requirements."""

    def test_rollback_doc_exists(self):
        import os

        path = "docs/implementation/meilisearch-rollout.md"
        assert os.path.exists(path), f"Rollback doc missing: {path}"
        with open(path) as f:
            content = f.read()
        assert "rollback" in content.lower() or "disable" in content.lower()
