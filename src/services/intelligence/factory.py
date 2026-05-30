"""Factory for building the active LLM generation provider."""

from __future__ import annotations

from shared.config import Settings

from .llm_provider import LLMProvider, OpenAICompatibleLLMProvider
from .ollama_client import OllamaClient

# Provider names that use the OpenAI-compatible /v1/chat/completions format.
_OPENAI_COMPATIBLE_PROVIDERS = frozenset(
    {
        "openai-compatible",
        "openai",
        "litellm",
        "llama-cpp",
    }
)


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Build and return an LLM provider based on *settings*.

    Provider resolution:
    - ``LLM_PROVIDER=ollama`` (default) — ``OllamaClient`` at ``LLM_BASE_URL``
      (falls back to ``OLLAMA_URL``) with ``LLM_MODEL`` (falls back to
      ``OLLAMA_MODEL``).
    - ``LLM_PROVIDER=openai-compatible`` — ``OpenAICompatibleLLMProvider``
      hitting ``/v1/chat/completions`` at the same base URL.
    - ``LLM_PROVIDER=openai`` — ``OpenAICompatibleLLMProvider`` with
      ``LLM_API_KEY`` (required).
    - ``LLM_PROVIDER=litellm`` — ``OpenAICompatibleLLMProvider`` (API key
      optional, set via ``LLM_API_KEY``).
    - ``LLM_PROVIDER=llama-cpp`` — ``OpenAICompatibleLLMProvider`` (no API key
      needed).

    Raises:
        ValueError: When the configured provider is unknown.
    """
    provider = settings.llm_provider or "ollama"
    base_url = settings.llm_base_url or settings.ollama_url
    model = settings.llm_model or settings.ollama_model

    if provider == "ollama":
        return OllamaClient(base_url=base_url, model=model)

    if provider in _OPENAI_COMPATIBLE_PROVIDERS:
        api_key: str | None = settings.llm_api_key or None
        if provider == "openai" and not api_key:
            raise ValueError(
                "LLM_PROVIDER=openai requires LLM_API_KEY to be set"
            )
        return OpenAICompatibleLLMProvider(
            base_url=base_url,
            model=model,
            api_key=api_key,
        )

    raise ValueError(f"Unknown LLM provider: {provider!r}")
