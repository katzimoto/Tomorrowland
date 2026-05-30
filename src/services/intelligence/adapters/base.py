"""Base adapter interface and capability models for model providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ProviderCapabilities:
    """Declared capabilities of a model provider adapter."""

    chat: bool = False
    embedding: bool = False
    vision: bool = False
    streaming: bool = False
    function_calling: bool = False

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderHealthResult:
    """Result of a provider health check."""

    healthy: bool
    latency_ms: float | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseModelProviderAdapter(Protocol):
    """Structural protocol for model provider adapters.

    Every provider adapter (Ollama, OpenAI-compatible, Anthropic, etc.)
    must satisfy this interface.  Concrete implementations live in sibling
    modules (e.g. ``adapters/ollama.py``, ``adapters/openai.py``) and are
    registered via the provider registry at runtime.

    This protocol is intentionally minimal — extension interfaces for chat,
    embedding, and generation are added in follow-up issues (#575, #576).
    """

    @property
    def provider_type(self) -> str:
        """Stable identifier for this provider kind (e.g. ``"ollama"``)."""
        ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Capabilities this adapter advertises."""
        ...

    async def check_health(self) -> ProviderHealthResult:
        """Ping the provider and return a health result.

        Implementations should time their own request and populate
        *latency_ms* on success, or set *healthy* to False and
        populate *error* on failure.
        """
        ...

    def __repr__(self) -> str:
        return f"<{type(self).__name__} provider_type={self.provider_type!r}>"
