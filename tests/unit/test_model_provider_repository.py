"""Unit tests for the model provider registry repository."""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.intelligence.model_provider_models import (
    ModelDescriptorCreate,
    ModelDescriptorUpdate,
    ModelProviderCreate,
    ModelProviderUpdate,
    ModelTaskDefaultCreate,
    ModelTaskDefaultUpdate,
)
from services.intelligence.model_provider_repository import ModelProviderRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(tmp_path) -> Engine:
    db_path = tmp_path / "test_model_provider.db"
    eng = create_engine(f"sqlite:///{db_path}")
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


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------


def test_create_provider(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        data = ModelProviderCreate(
            name="Test Ollama",
            provider_type="ollama",
            base_url="http://ollama:11434",
            locality="local",
        )
        provider = repo.create_provider(data)
        assert provider.name == "Test Ollama"
        assert provider.provider_type == "ollama"
        assert provider.locality == "local"
        assert provider.enabled is True


def test_get_provider(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        data = ModelProviderCreate(name="My Provider", provider_type="openai-compatible")
        created = repo.create_provider(data)
        fetched = repo.get_provider(created.id)
        assert fetched is not None
        assert fetched.name == "My Provider"
        assert fetched.id == created.id


def test_get_provider_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.get_provider(uuid4()) is None


def test_get_provider_by_name(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        data = ModelProviderCreate(name="ByName", provider_type="ollama")
        created = repo.create_provider(data)
        fetched = repo.get_provider_by_name("ByName")
        assert fetched is not None
        assert fetched.id == created.id


def test_get_provider_by_name_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.get_provider_by_name("DoesNotExist") is None


def test_list_providers(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        repo.create_provider(ModelProviderCreate(name="A", provider_type="ollama"))
        repo.create_provider(ModelProviderCreate(name="B", provider_type="openai-compatible"))
        all_providers = repo.list_providers()
        assert len(all_providers) == 2


def test_list_providers_enabled_only(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        repo.create_provider(ModelProviderCreate(name="Active", provider_type="ollama"))
        repo.create_provider(
            ModelProviderCreate(name="Disabled", provider_type="ollama", enabled=False)
        )
        enabled = repo.list_providers(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].name == "Active"


def test_update_provider(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        created = repo.create_provider(ModelProviderCreate(name="Orig", provider_type="ollama"))
        updated = repo.update_provider(
            created.id, ModelProviderUpdate(name="Updated", enabled=False)
        )
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.enabled is False


def test_update_provider_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.update_provider(uuid4(), ModelProviderUpdate(name="Nope")) is None


def test_delete_provider(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        created = repo.create_provider(ModelProviderCreate(name="DeleteMe", provider_type="ollama"))
        assert repo.delete_provider(created.id) is True
        assert repo.get_provider(created.id) is None


def test_delete_provider_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.delete_provider(uuid4()) is False


# ---------------------------------------------------------------------------
# Descriptor CRUD
# ---------------------------------------------------------------------------


def test_create_descriptor(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="DescTest", provider_type="ollama"))
        desc = repo.create_descriptor(
            ModelDescriptorCreate(
                provider_id=prov.id,
                model_name="mistral",
                display_name="Mistral 7B",
                context_window=8192,
            )
        )
        assert desc.model_name == "mistral"
        assert desc.display_name == "Mistral 7B"
        assert desc.context_window == 8192
        assert desc.provider_id == prov.id


def test_get_descriptor(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="GetDesc", provider_type="ollama"))
        created = repo.create_descriptor(
            ModelDescriptorCreate(provider_id=prov.id, model_name="llama3")
        )
        fetched = repo.get_descriptor(created.id)
        assert fetched is not None
        assert fetched.model_name == "llama3"


def test_get_descriptor_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.get_descriptor(uuid4()) is None


def test_list_descriptors_by_provider(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov1 = repo.create_provider(ModelProviderCreate(name="P1", provider_type="ollama"))
        prov2 = repo.create_provider(
            ModelProviderCreate(name="P2", provider_type="openai-compatible")
        )
        repo.create_descriptor(ModelDescriptorCreate(provider_id=prov1.id, model_name="m1"))
        repo.create_descriptor(ModelDescriptorCreate(provider_id=prov1.id, model_name="m2"))
        repo.create_descriptor(ModelDescriptorCreate(provider_id=prov2.id, model_name="m3"))
        p1_descs = repo.list_descriptors(provider_id=prov1.id)
        assert len(p1_descs) == 2
        all_descs = repo.list_descriptors()
        assert len(all_descs) == 3


def test_list_descriptors_enabled_only(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="EOnly", provider_type="ollama"))
        repo.create_descriptor(ModelDescriptorCreate(provider_id=prov.id, model_name="active"))
        repo.create_descriptor(
            ModelDescriptorCreate(provider_id=prov.id, model_name="disabled", enabled=False)
        )
        enabled = repo.list_descriptors(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].model_name == "active"


def test_update_descriptor(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="UpdDesc", provider_type="ollama"))
        created = repo.create_descriptor(
            ModelDescriptorCreate(provider_id=prov.id, model_name="orig")
        )
        updated = repo.update_descriptor(
            created.id,
            ModelDescriptorUpdate(display_name="Updated Display", context_window=4096),
        )
        assert updated is not None
        assert updated.display_name == "Updated Display"
        assert updated.context_window == 4096


def test_update_descriptor_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.update_descriptor(uuid4(), ModelDescriptorUpdate(display_name="X")) is None


def test_delete_descriptor(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="DelDesc", provider_type="ollama"))
        created = repo.create_descriptor(
            ModelDescriptorCreate(provider_id=prov.id, model_name="delete-me")
        )
        assert repo.delete_descriptor(created.id) is True
        assert repo.get_descriptor(created.id) is None


# ---------------------------------------------------------------------------
# Descriptor uniqueness
# ---------------------------------------------------------------------------


def test_descriptor_unique_provider_model(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="Uniq", provider_type="ollama"))
        repo.create_descriptor(
            ModelDescriptorCreate(provider_id=prov.id, model_name="unique-model")
        )
        with pytest.raises(sa.exc.IntegrityError):
            repo.create_descriptor(
                ModelDescriptorCreate(provider_id=prov.id, model_name="unique-model")
            )


def test_same_model_name_different_providers(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        p1 = repo.create_provider(ModelProviderCreate(name="P1", provider_type="ollama"))
        p2 = repo.create_provider(ModelProviderCreate(name="P2", provider_type="openai-compatible"))
        repo.create_descriptor(ModelDescriptorCreate(provider_id=p1.id, model_name="shared-model"))
        # Same model name under a different provider is allowed
        repo.create_descriptor(ModelDescriptorCreate(provider_id=p2.id, model_name="shared-model"))
        assert len(repo.list_descriptors()) == 2


# ---------------------------------------------------------------------------
# Task default CRUD
# ---------------------------------------------------------------------------


def test_set_task_default(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="TaskDef", provider_type="ollama"))
        td = repo.set_task_default(ModelTaskDefaultCreate(task_type="chat", provider_id=prov.id))
        assert td.task_type == "chat"
        assert td.provider_id == prov.id


def test_set_task_default_upsert(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        p1 = repo.create_provider(ModelProviderCreate(name="TD1", provider_type="ollama"))
        p2 = repo.create_provider(
            ModelProviderCreate(name="TD2", provider_type="openai-compatible")
        )
        original = repo.set_task_default(ModelTaskDefaultCreate(task_type="summary", provider_id=p1.id))
        # Upsert — same task_type, different provider
        upserted = repo.set_task_default(
            ModelTaskDefaultCreate(task_type="summary", provider_id=p2.id)
        )
        assert upserted.provider_id == p2.id
        # id must be the original row's id, not a freshly generated one
        assert upserted.id == original.id
        all_defaults = repo.list_task_defaults()
        assert len(all_defaults) == 1


def test_get_task_default(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="GetTD", provider_type="ollama"))
        repo.set_task_default(ModelTaskDefaultCreate(task_type="embedding", provider_id=prov.id))
        fetched = repo.get_task_default("embedding")
        assert fetched is not None
        assert fetched.task_type == "embedding"


def test_get_task_default_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.get_task_default("nonexistent") is None


def test_list_task_defaults(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="ListTD", provider_type="ollama"))
        repo.set_task_default(ModelTaskDefaultCreate(task_type="chat", provider_id=prov.id))
        repo.set_task_default(ModelTaskDefaultCreate(task_type="summary", provider_id=prov.id))
        all_defaults = repo.list_task_defaults()
        assert len(all_defaults) == 2


def test_update_task_default(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        p1 = repo.create_provider(ModelProviderCreate(name="UTDP1", provider_type="ollama"))
        p2 = repo.create_provider(
            ModelProviderCreate(name="UTDP2", provider_type="openai-compatible")
        )
        repo.set_task_default(ModelTaskDefaultCreate(task_type="chat", provider_id=p1.id))
        updated = repo.update_task_default("chat", ModelTaskDefaultUpdate(provider_id=p2.id))
        assert updated is not None
        assert updated.provider_id == p2.id


def test_update_task_default_not_found(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        assert repo.update_task_default("missing", ModelTaskDefaultUpdate()) is None


def test_delete_task_default(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="DelTD", provider_type="ollama"))
        repo.set_task_default(ModelTaskDefaultCreate(task_type="translate", provider_id=prov.id))
        assert repo.delete_task_default("translate") is True
        assert repo.get_task_default("translate") is None


# ---------------------------------------------------------------------------
# Cascade behavior
# ---------------------------------------------------------------------------


def test_delete_provider_cascades_to_descriptors(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="Cascade", provider_type="ollama"))
        repo.create_descriptor(ModelDescriptorCreate(provider_id=prov.id, model_name="child-a"))
        repo.create_descriptor(ModelDescriptorCreate(provider_id=prov.id, model_name="child-b"))
        assert len(repo.list_descriptors(provider_id=prov.id)) == 2
        repo.delete_provider(prov.id)
        assert len(repo.list_descriptors()) == 0


def test_delete_provider_cascades_to_task_defaults(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(ModelProviderCreate(name="CascadeTD", provider_type="ollama"))
        repo.set_task_default(ModelTaskDefaultCreate(task_type="chat", provider_id=prov.id))
        repo.set_task_default(ModelTaskDefaultCreate(task_type="summary", provider_id=prov.id))
        assert len(repo.list_task_defaults()) == 2
        repo.delete_provider(prov.id)
        assert len(repo.list_task_defaults()) == 0


# ---------------------------------------------------------------------------
# Credential safety
# ---------------------------------------------------------------------------


def test_no_raw_credential_storage(engine: Engine) -> None:
    """Verify that the repository never stores raw credential values.

    The *api_key_ref* field is a reference, not the secret itself.
    """
    with engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        ref_value = "vault://providers/my-ollama/key"
        prov = repo.create_provider(
            ModelProviderCreate(
                name="SafeCreds",
                provider_type="ollama",
                api_key_ref=ref_value,
            )
        )
        assert prov.api_key_ref == ref_value
        fetched = repo.get_provider(prov.id)
        assert fetched is not None
        assert fetched.api_key_ref == ref_value
        # Verify no other credential-related fields exist
        assert not hasattr(fetched, "api_key")
        assert not hasattr(fetched, "api_secret")
