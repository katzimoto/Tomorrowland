"""Factory for building the active LLM generation provider."""

from __future__ import annotations

from shared.config import Settings

from .llm_provider import LLMProvider, OpenAICompatibleLLMProvider
from .ollama_client import OllamaClient


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Build and return an LLM provider based on *settings*.

    Provider resolution:
    - ``LLM_PROVIDER=ollama`` (default) — ``OllamaClient`` at ``LLM_BASE_URL``
      (falls back to ``OLLAMA_URL``) with ``LLM_MODEL`` (falls back to
      ``OLLAMA_MODEL``).
    - ``LLM_PROVIDER=openai-compatible`` — ``OpenAICompatibleLLMProvider``
      hitting ``/v1/chat/completions`` at the same base URL.

    Raises:
        ValueError: When the configured provider is unknown.
    """
    provider = settings.llm_provider or "ollama"
    base_url = settings.llm_base_url or settings.ollama_url
    model = settings.llm_model or settings.ollama_model

    if provider == "ollama":
        return OllamaClient(base_url=base_url, model=model)

    if provider == "openai-compatible":
        return OpenAICompatibleLLMProvider(base_url=base_url, model=model)

    raise ValueError(f"Unknown LLM provider: {provider!r}")
