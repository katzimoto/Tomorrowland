"""Canonical model-runtime boundary (#813).

``ModelRuntime`` is the single boundary product code should call to obtain a
model client for a named *task/purpose* (``"chat"``, ``"utility"``,
``"reranking"``, ``"source_qa"``, ...).  Callers request a purpose; only the
runtime knows provider details, DB/env precedence, credentials, and air-gap
policy.

Precedence (per task):

    DB admin task default (TaskDefaultResolver)  >  env/bundled fallback (build_llm_provider)

Air-gap policy: when ``settings.air_gapped`` is true, a DB task default that
resolves to an ``external`` (cloud/SaaS) provider is refused and the task falls
back to the local env/bundled provider — air-gapped deployments never silently
egress to an external provider.

This wraps the existing foundation (``TaskDefaultResolver``,
``build_llm_provider``, ``ProviderRegistry``) rather than introducing a parallel
registry. Do not construct ``OllamaClient`` / ``OpenAICompatibleLLMProvider`` /
``build_llm_provider`` directly in product code — go through this runtime. A
guardrail test (``tests/unit/test_no_direct_model_construction.py``) enforces
this.
"""

from __future__ import annotations

import logging

from services.intelligence.llm_provider import LLMProvider
from services.intelligence.provider_registry import ProviderRegistry
from services.intelligence.task_defaults import (
    TaskDefaultResolver,
    TaskResolution,
    build_llm_from_resolution,
)
from shared.config import Settings

logger = logging.getLogger(__name__)

_EXTERNAL_LOCALITY = "external"


class ModelRuntime:
    """Single runtime boundary for resolving model providers by purpose."""

    def __init__(
        self,
        settings: Settings,
        env_provider: LLMProvider,
        resolver: TaskDefaultResolver | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._env_provider = env_provider
        self._resolver = resolver
        self._provider_registry = provider_registry

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve_task(self, task: str) -> TaskResolution | None:
        """Resolve *task* to a DB task default, applying air-gap policy.

        Returns ``None`` when no usable DB default exists (caller falls back to
        the env/bundled provider).
        """
        resolver = self._resolver
        if resolver is None or not resolver.loaded:
            return None
        resolution = resolver.resolve(task)
        if resolution is None:
            return None
        if self._settings.air_gapped and resolution.locality == _EXTERNAL_LOCALITY:
            logger.warning(
                "air-gapped mode: refusing external provider %r for task %r — env fallback",
                resolution.provider_name,
                task,
            )
            return None
        return resolution

    def get_chat_provider(self, task: str = "chat") -> LLMProvider:
        """Return an :class:`LLMProvider` for *task* (DB default → env fallback)."""
        resolution = self.resolve_task(task)
        if resolution is not None:
            try:
                return build_llm_from_resolution(resolution)
            except ValueError:
                logger.warning(
                    "task %r resolved to an unsupported provider type — env fallback",
                    task,
                )
        return self._env_provider

    def effective_model_name(self, task: str, fallback: str) -> str:
        """Return the DB-default model name for *task*, or *fallback*."""
        resolution = self.resolve_task(task)
        if resolution is not None and resolution.model_name:
            return resolution.model_name
        return fallback

    def effective_source(self, task: str) -> str:
        """Return ``"db_task_default"`` or ``"env_fallback"`` for diagnostics/UI."""
        return "db_task_default" if self.resolve_task(task) is not None else "env_fallback"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Reload underlying resolver + provider registry from the database."""
        if self._resolver is not None:
            self._resolver.reload()
        if self._provider_registry is not None:
            self._provider_registry.reload()
