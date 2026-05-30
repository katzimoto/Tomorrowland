"""Task default resolution for model provider dispatch.

Resolves model providers for named task types (``"chat"``, ``"utility"``,
``"reranking"``, ``"embedding"``, etc.) from the DB-backed
``model_task_defaults`` table.

When no DB row exists for a task type the resolver returns None — callers
fall back to their existing environment / settings behaviour unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Engine

from services.intelligence.credential_store import CredentialStore
from services.intelligence.llm_provider import LLMProvider, OpenAICompatibleLLMProvider
from services.intelligence.model_provider_models import (
    ModelDescriptor,
    ModelProvider,
    ModelTaskDefault,
)
from services.intelligence.model_provider_repository import ModelProviderRepository
from services.intelligence.ollama_client import OllamaClient
from shared.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class TaskResolution:
    """Resolution result for a model task type.

    Returned by :meth:`TaskDefaultResolver.resolve`.  Every field is
    *None*-safe — callers must check *model_name* before using it.
    """

    provider_name: str
    provider_type: str
    model_name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    locality: str = "local"
    parameters: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Public helpers (no secrets logged)
# ---------------------------------------------------------------------------


def build_llm_from_resolution(resolution: TaskResolution) -> LLMProvider:
    """Build an ``LLMProvider`` from a resolved task default.

    Args:
        resolution: A non-``None`` :class:`TaskResolution`.

    Returns:
        An :class:`OllamaClient` or :class:`OpenAICompatibleLLMProvider`.

    Raises:
        ValueError: When the provider type is not supported for
            LLM generation.
    """
    provider_type = resolution.provider_type
    base_url = resolution.base_url or ""
    model = resolution.model_name or ""
    api_key = resolution.api_key

    if provider_type == "ollama":
        return OllamaClient(base_url=base_url, model=model)

    if provider_type in frozenset({"openai-compatible", "openai", "litellm", "llama-cpp"}):
        return OpenAICompatibleLLMProvider(
            base_url=base_url,
            model=model,
            api_key=api_key,
        )

    raise ValueError(f"Unsupported LLM provider type for task default: {provider_type!r}")


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class TaskDefaultResolver:
    """In-memory resolver for ``model_task_defaults`` rows.

    Usage::

        resolver = TaskDefaultResolver(engine, settings, "cred-key")
        resolver.load()          # one-shot at startup
        res = resolver.resolve("chat")
        if res is None:
            llm = build_llm_provider(settings)   # env fallback
        else:
            llm = build_llm_from_resolution(res)

    Falls back to *None* (env behaviour) when:

    * the task type has no DB row;
    * the configured provider is missing or disabled;
    * the configured model descriptor is disabled.

    No credential values are exposed in logs or error messages.
    """

    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        credential_store_key: str,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._credential_store_key = credential_store_key
        self._defaults: dict[str, ModelTaskDefault] = {}
        self._providers: dict[UUID, ModelProvider] = {}
        self._descriptors: dict[UUID, ModelDescriptor] = {}
        self._api_keys: dict[str, str] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load all task defaults, providers, descriptors, and API keys.

        Idempotent — subsequent calls reload from the database.
        """
        self._defaults = {}
        self._providers = {}
        self._descriptors = {}
        self._api_keys = {}

        with self._engine.begin() as conn:
            repo = ModelProviderRepository(conn)
            defaults = repo.list_task_defaults()
            providers = repo.list_providers()
            descriptors = repo.list_descriptors()

            self._defaults = {d.task_type: d for d in defaults}
            self._providers = {p.id: p for p in providers}
            self._descriptors = {d.id: d for d in descriptors}

            credential_store = CredentialStore(conn, self._credential_store_key)
            for prov in providers:
                if prov.api_key_ref:
                    key = credential_store.get_credential(prov.api_key_ref)
                    if key is not None:
                        self._api_keys[prov.name] = key

        self._loaded = True
        logger.info(
            "TaskDefaultResolver loaded %d default(s), %d provider(s), %d descriptor(s)",
            len(self._defaults),
            len(self._providers),
            len(self._descriptors),
        )

    def reload(self) -> None:
        """Reload all data from the database."""
        self.load()

    @property
    def loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, task_type: str) -> TaskResolution | None:
        """Resolve *task_type* to provider+model info.

        Returns *None* when no DB default exists (caller keeps env behaviour).
        """
        default = self._defaults.get(task_type)
        if default is None:
            return None

        provider = self._providers.get(default.provider_id)
        if provider is None:
            logger.warning(
                "TaskDefaultResolver: task_type=%r references missing provider_id=%s",
                task_type,
                default.provider_id,
            )
            return None

        if not provider.enabled:
            logger.info(
                "TaskDefaultResolver: task_type=%r provider=%r is disabled — falling back",
                task_type,
                provider.name,
            )
            return None

        model_name: str | None = None
        if default.model_descriptor_id is not None:
            descriptor = self._descriptors.get(default.model_descriptor_id)
            if descriptor is None:
                logger.warning(
                    "TaskDefaultResolver: task_type=%r references missing "
                    "descriptor_id=%s — falling back to None",
                    task_type,
                    default.model_descriptor_id,
                )
                return None
            elif not descriptor.enabled:
                logger.info(
                    "TaskDefaultResolver: task_type=%r descriptor model=%r is disabled — "
                    "falling back to None",
                    task_type,
                    descriptor.model_name,
                )
                return None
            else:
                model_name = descriptor.model_name

        api_key = self._api_keys.get(provider.name)
        base_url = provider.base_url

        logger.debug(
            "TaskDefaultResolver resolved task_type=%r -> provider=%r model=%r "
            "base_url=%r api_key_set=%s",
            task_type,
            provider.name,
            model_name,
            base_url,
            api_key is not None,
        )

        return TaskResolution(
            provider_name=provider.name,
            provider_type=provider.provider_type,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            locality=provider.locality,
            parameters=default.parameters,
        )

    def build_llm_provider(self, task_type: str) -> LLMProvider | None:
        """Build an :class:`LLMProvider` from a DB default.

        Returns *None* when no DB default exists or when the configured
        descriptor is disabled/missing (env fallback).
        """
        resolution = self.resolve(task_type)
        if resolution is None:
            return None
        return build_llm_from_resolution(resolution)
