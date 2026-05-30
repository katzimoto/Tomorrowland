"""Unit tests for TaskDefaultResolver and build_llm_from_resolution."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.intelligence.llm_provider import OpenAICompatibleLLMProvider
from services.intelligence.model_provider_models import (
    ModelDescriptorCreate,
    ModelProviderCreate,
    ModelTaskDefaultCreate,
)
from services.intelligence.model_provider_repository import ModelProviderRepository
from services.intelligence.ollama_client import OllamaClient
from services.intelligence.task_defaults import (
    TaskDefaultResolver,
    TaskResolution,
    build_llm_from_resolution,
)
from shared.config import Settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        conn.execute(
            sa.text("""
                CREATE TABLE model_descriptors (
                    id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL REFERENCES model_providers(id) ON DELETE CASCADE,
                    model_name TEXT NOT NULL,
                    display_name TEXT,
                    description TEXT,
                    capabilities TEXT,
                    context_window INTEGER,
                    max_output_tokens INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    UNIQUE (provider_id, model_name)
                )
            """)
        )
        conn.execute(
            sa.text("""
                CREATE TABLE model_task_defaults (
                    id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    provider_id TEXT NOT NULL REFERENCES model_providers(id) ON DELETE CASCADE,
                    model_descriptor_id TEXT REFERENCES model_descriptors(id) ON DELETE SET NULL,
                    parameters TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    UNIQUE (task_type)
                )
            """)
        )
    return eng


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def resolver(engine: Engine) -> TaskDefaultResolver:
    return TaskDefaultResolver(engine, Settings(), "test-key")


# ---------------------------------------------------------------------------
# Empty DB — env fallback
# ---------------------------------------------------------------------------


def test_resolver_returns_none_for_empty_db(resolver: TaskDefaultResolver) -> None:
    resolver.load()
    assert resolver.resolve("chat") is None
    assert resolver.resolve("utility") is None
    assert resolver.resolve("reranking") is None
    assert resolver.resolve("embedding") is None
    assert resolver.build_llm_provider("chat") is None


def test_resolver_loaded_flag(engine: Engine) -> None:
    r = TaskDefaultResolver(engine, Settings(), "test-key")
    assert r.loaded is False
    r.load()
    assert r.loaded is True


# ---------------------------------------------------------------------------
# Resolver with DB defaults
# ---------------------------------------------------------------------------


def test_resolver_returns_task_default_when_present(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="Ollama",
                provider_type="ollama",
                base_url="http://ollama:11434",
                enabled=True,
            )
        )
        desc = repo.create_descriptor(
            ModelDescriptorCreate(
                provider_id=prov.id,
                model_name="qwen3:35b",
                enabled=True,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
                model_descriptor_id=desc.id,
            )
        )
    resolver.load()
    res = resolver.resolve("chat")
    assert res is not None
    assert res.provider_name == "Ollama"
    assert res.provider_type == "ollama"
    assert res.model_name == "qwen3:35b"
    assert res.base_url == "http://ollama:11434"
    assert res.api_key is None


def test_resolver_without_descriptor(engine: Engine, resolver: TaskDefaultResolver) -> None:
    """When no descriptor is specified, model_name is None."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="Ollama",
                provider_type="ollama",
                base_url="http://ollama:11434",
                enabled=True,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
                model_descriptor_id=None,
            )
        )
    resolver.load()
    res = resolver.resolve("chat")
    assert res is not None
    assert res.provider_name == "Ollama"
    assert res.model_name is None


def test_resolver_disabled_provider_falls_back(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    """Disabled provider → resolve returns None (env fallback)."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="DisabledProv",
                provider_type="ollama",
                enabled=False,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
            )
        )
    resolver.load()
    assert resolver.resolve("chat") is None


def test_resolver_missing_provider_falls_back(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    """Provider deleted after default was set → resolve returns None."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="Temp",
                provider_type="ollama",
                enabled=True,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
            )
        )
        # Delete the provider — default orphaned
        repo.delete_provider(prov.id)
    resolver.load()
    assert resolver.resolve("chat") is None


def test_resolver_disabled_descriptor_falls_back(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    """Disabled descriptor → resolve returns None (env fallback), not a partial
    resolution with model_name=None that would create a provider with empty model."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="Ollama",
                provider_type="ollama",
                enabled=True,
            )
        )
        desc = repo.create_descriptor(
            ModelDescriptorCreate(
                provider_id=prov.id,
                model_name="old-model",
                enabled=False,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
                model_descriptor_id=desc.id,
            )
        )
    resolver.load()
    assert resolver.resolve("chat") is None


def test_resolver_deleted_descriptor_behaves_like_no_descriptor(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    """Descriptor deleted after default → ON DELETE SET NULL nulls model_descriptor_id,
    so the task default behaves as if no descriptor was ever configured: resolve()
    returns a TaskResolution with model_name=None (use provider default model)."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="Ollama",
                provider_type="ollama",
                enabled=True,
            )
        )
        desc = repo.create_descriptor(
            ModelDescriptorCreate(
                provider_id=prov.id,
                model_name="ghost-model",
                enabled=True,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
                model_descriptor_id=desc.id,
            )
        )
        # ON DELETE SET NULL: model_descriptor_id becomes NULL on deletion
        repo.delete_descriptor(desc.id)
    resolver.load()
    res = resolver.resolve("chat")
    assert res is not None
    assert res.provider_name == "Ollama"
    assert res.model_name is None


# ---------------------------------------------------------------------------
# build_llm_provider
# ---------------------------------------------------------------------------


def test_build_llm_provider_returns_none_for_empty_db(
    resolver: TaskDefaultResolver,
) -> None:
    resolver.load()
    assert resolver.build_llm_provider("chat") is None


def test_build_llm_provider_returns_ollama_client(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="LocalOllama",
                provider_type="ollama",
                base_url="http://ollama:11434",
                enabled=True,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
            )
        )
    resolver.load()
    llm = resolver.build_llm_provider("chat")
    assert llm is not None
    assert isinstance(llm, OllamaClient)


def test_build_llm_provider_returns_openai_compatible(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="OpenAIProxy",
                provider_type="openai-compatible",
                base_url="http://proxy:8000",
                enabled=True,
            )
        )
        desc = repo.create_descriptor(
            ModelDescriptorCreate(
                provider_id=prov.id,
                model_name="gpt-4o-mini",
                enabled=True,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
                model_descriptor_id=desc.id,
            )
        )
    resolver.load()
    llm = resolver.build_llm_provider("chat")
    assert llm is not None
    assert isinstance(llm, OpenAICompatibleLLMProvider)
    assert llm.model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# build_llm_from_resolution
# ---------------------------------------------------------------------------


def test_build_llm_from_resolution_ollama() -> None:
    res = TaskResolution(
        provider_name="Ollama",
        provider_type="ollama",
        model_name="qwen3:8b",
        base_url="http://ollama:11434",
    )
    llm = build_llm_from_resolution(res)
    assert isinstance(llm, OllamaClient)
    assert llm.model == "qwen3:8b"


def test_build_llm_from_resolution_openai_compatible() -> None:
    res = TaskResolution(
        provider_name="OpenAI",
        provider_type="openai-compatible",
        model_name="gpt-4o",
        base_url="https://api.openai.com",
        api_key="sk-test123",
    )
    llm = build_llm_from_resolution(res)
    assert isinstance(llm, OpenAICompatibleLLMProvider)
    assert llm.model == "gpt-4o"


def test_build_llm_from_resolution_unsupported() -> None:
    res = TaskResolution(
        provider_name="Custom",
        provider_type="anthropic",
        model_name="claude-3",
    )
    with pytest.raises(ValueError, match="Unsupported LLM provider type"):
        build_llm_from_resolution(res)


# ---------------------------------------------------------------------------
# Multiple task types
# ---------------------------------------------------------------------------


def test_resolver_handles_multiple_task_types(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(name="Ollama", provider_type="ollama", enabled=True)
        )
        repo.set_task_default(ModelTaskDefaultCreate(task_type="chat", provider_id=prov.id))
        repo.set_task_default(ModelTaskDefaultCreate(task_type="utility", provider_id=prov.id))
    resolver.load()
    assert resolver.resolve("chat") is not None
    assert resolver.resolve("utility") is not None
    assert resolver.resolve("reranking") is None  # not configured


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------


def test_reload_picks_up_new_defaults(engine: Engine, resolver: TaskDefaultResolver) -> None:
    resolver.load()
    assert resolver.resolve("chat") is None

    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(name="NewProv", provider_type="ollama", enabled=True)
        )
        repo.set_task_default(ModelTaskDefaultCreate(task_type="chat", provider_id=prov.id))

    resolver.reload()
    assert resolver.resolve("chat") is not None


# ---------------------------------------------------------------------------
# Parameters passthrough
# ---------------------------------------------------------------------------


def test_resolver_passes_parameters(engine: Engine, resolver: TaskDefaultResolver) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(name="Ollama", provider_type="ollama", enabled=True)
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
                parameters={"temperature": 0.7, "max_tokens": 2048},
            )
        )
    resolver.load()
    res = resolver.resolve("chat")
    assert res is not None
    assert res.parameters == {"temperature": 0.7, "max_tokens": 2048}


# ---------------------------------------------------------------------------
# No secret leakage
# ---------------------------------------------------------------------------


def test_resolver_does_not_expose_api_key_in_string(
    engine: Engine, resolver: TaskDefaultResolver, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify the log message does not contain the raw API key."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="External",
                provider_type="openai-compatible",
                base_url="https://api.example.com",
                enabled=True,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
            )
        )
    resolver.load()
    # Override the cached API key with a known test value
    resolver._api_keys["External"] = "sk-abc123def456"

    res = resolver.resolve("chat")
    assert res is not None
    assert res.api_key == "sk-abc123def456"  # returned to caller but not logged
    # Verify no log message contains the raw key
    for record in caplog.records:
        assert "sk-abc123def456" not in record.message


# ---------------------------------------------------------------------------
# build_llm_provider — disabled/missing descriptor fallback
# ---------------------------------------------------------------------------


def test_build_llm_provider_disabled_descriptor_returns_none(
    engine: Engine, resolver: TaskDefaultResolver
) -> None:
    """Disabled descriptor → build_llm_provider returns None, not a provider with
    empty model name that silently bypasses the env fallback chain."""
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="Ollama",
                provider_type="ollama",
                base_url="http://ollama:11434",
                enabled=True,
            )
        )
        desc = repo.create_descriptor(
            ModelDescriptorCreate(
                provider_id=prov.id,
                model_name="disabled-model",
                enabled=False,
            )
        )
        repo.set_task_default(
            ModelTaskDefaultCreate(
                task_type="chat",
                provider_id=prov.id,
                model_descriptor_id=desc.id,
            )
        )
    resolver.load()
    assert resolver.build_llm_provider("chat") is None
