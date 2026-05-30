"""Unit tests for ProviderRegistry."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.intelligence.model_provider_models import ModelProviderCreate
from services.intelligence.model_provider_repository import ModelProviderRepository
from services.intelligence.provider_registry import ProviderRegistry


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("PRAGMA foreign_keys = ON"))
        conn.execute(
            sa.text("""
                CREATE TABLE model_providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    description TEXT,
                    base_url TEXT,
                    api_key_ref TEXT,
                    locality TEXT NOT NULL DEFAULT 'local',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    UNIQUE (name)
                )
            """)
        )
    return eng


def test_registry_empty_when_no_providers(engine: Engine) -> None:
    reg = ProviderRegistry(engine, "test-key")
    reg.load()
    assert reg.loaded is True
    assert reg.provider_count() == 0
    assert reg.adapters == {}


def test_registry_loads_enabled_providers(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        repo.create_provider(
            ModelProviderCreate(name="Ollama", provider_type="ollama", enabled=True)
        )
        repo.create_provider(
            ModelProviderCreate(name="Disabled", provider_type="openai-compatible", enabled=False)
        )

    reg = ProviderRegistry(engine, "test-key")
    reg.load()
    assert reg.provider_count() == 1  # only enabled providers
    assert reg.provider_names() == ["Ollama"]
    assert reg.get_provider("Ollama") is not None
    # no concrete adapter yet (_build_adapter returns None)
    assert reg.get_adapter("Ollama") is None


def test_reload_rebuilds_adapters(engine: Engine) -> None:
    reg = ProviderRegistry(engine, "test-key")
    reg.load()
    assert reg.provider_count() == 0

    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        repo.create_provider(ModelProviderCreate(name="New", provider_type="ollama"))

    reg.reload()
    assert reg.provider_count() == 1


def test_get_adapter_returns_none_for_missing(engine: Engine) -> None:
    reg = ProviderRegistry(engine, "test-key")
    reg.load()
    assert reg.get_adapter("nonexistent") is None
    assert reg.get_provider("nonexistent") is None


def test_registry_loaded_flag(engine: Engine) -> None:
    reg = ProviderRegistry(engine, "test-key")
    assert reg.loaded is False
    reg.load()
    assert reg.loaded is True


def test_registry_does_not_affect_repository(engine: Engine) -> None:
    """Verify registry load() doesn't modify the DB."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        repo.create_provider(ModelProviderCreate(name="Stable", provider_type="ollama"))

    reg = ProviderRegistry(engine, "test-key")
    reg.load()

    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        providers = repo.list_providers()
        assert len(providers) == 1
        assert providers[0].name == "Stable"


def test_provider_names_and_get_provider(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        p = repo.create_provider(ModelProviderCreate(name="MyProv", provider_type="ollama"))

    reg = ProviderRegistry(engine, "test-key")
    reg.load()
    assert reg.provider_names() == ["MyProv"]
    loaded = reg.get_provider("MyProv")
    assert loaded is not None
    assert loaded.id == p.id
