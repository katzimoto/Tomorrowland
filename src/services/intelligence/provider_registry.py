"""Runtime registry of model provider adapters.

The ``ProviderRegistry`` loads provider configuration from the database and
manages adapter instances.  It is wired into ``app.state`` but is **not** used
by chat / RAG / embedding / intelligence consumers yet — that change is
:issue:`578`.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Engine

from services.intelligence.adapters import BaseModelProviderAdapter
from services.intelligence.model_provider_repository import ModelProviderRepository

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """In-memory registry of model provider adapters.

    Loads provider metadata from the database and manages adapter instances.
    Currently a store of configuration; adapter instantiation is added when
    concrete adapters are wired in :issue:`578`.
    """

    def __init__(
        self,
        engine: Engine,
        credential_store_key: str,
    ) -> None:
        self._engine = engine
        self._credential_store_key = credential_store_key
        self._providers: dict[str, Any] = {}
        self._adapters: dict[str, BaseModelProviderAdapter] = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load all enabled providers from the database and build adapters.

        Idempotent — subsequent calls replace the adapter map.
        """
        self._providers = {}
        self._adapters = {}
        with self._engine.begin() as connection:
            repo = ModelProviderRepository(connection)
            providers = repo.list_providers(enabled_only=True)
            for prov in providers:
                self._providers[prov.name] = prov
                adapter = self._build_adapter(prov)
                if adapter is not None:
                    self._adapters[prov.name] = adapter
        self._loaded = True
        logger.info(
            "ProviderRegistry loaded %d provider(s), %d adapter(s)",
            len(self._providers),
            len(self._adapters),
        )

    def reload(self) -> None:
        """Rebuild all adapters from current database state."""
        self.load()

    @property
    def loaded(self) -> bool:
        """True after :meth:`load` or :meth:`reload` has been called."""
        return self._loaded

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def adapters(self) -> dict[str, BaseModelProviderAdapter]:
        """Return the current adapter map keyed by provider name."""
        return dict(self._adapters)

    def get_adapter(self, provider_name: str) -> BaseModelProviderAdapter | None:
        """Return the adapter for *provider_name*, or *None*."""
        return self._adapters.get(provider_name)

    def get_provider(self, provider_name: str) -> Any | None:
        """Return the ``ModelProvider`` config for *provider_name*, or *None*."""
        return self._providers.get(provider_name)

    def provider_count(self) -> int:
        """Number of loaded providers."""
        return len(self._providers)

    def provider_names(self) -> list[str]:
        """Names of all loaded providers."""
        return list(self._providers.keys())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_adapter(self, provider: Any) -> BaseModelProviderAdapter | None:
        """Build an adapter instance for a ``ModelProvider`` row.

        Returns *None* when the provider type is not yet supported (concrete
        adapter implementations will be added in :issue:`578`).
        """
        _ = provider
        logger.debug(
            "ProviderRegistry._build_adapter: no concrete adapters yet for %s",
            provider,
        )
        return None
