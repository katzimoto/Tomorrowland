from __future__ import annotations

import logging
from typing import Any

from shared.config import Settings

from .encoder import (
    DeterministicTestEncoder,
    OllamaEmbeddingEncoder,
    OpenAICompatibleEmbeddingEncoder,
    TextEncoder,
)
from .reranker import (
    EndpointSearchReranker,
    LLMSearchReranker,
    NoOpSearchReranker,
    SearchReranker,
)

logger = logging.getLogger(__name__)


def _resolution_dimension(resolution: Any, settings: Settings) -> int:
    """Embedding dimension from a task default's parameters, else settings.

    A task default may carry ``{"dimension": N}`` (or ``embedding_dimension``)
    in its parameters; otherwise the environment value is used. Changing the
    dimension still requires a re-index.
    """
    params = getattr(resolution, "parameters", None)
    if params:
        raw = params.get("dimension") or params.get("embedding_dimension")
        if raw is not None:
            return int(raw)
    return settings.embedding_dimension


def build_encoder(
    settings: Settings,
    *,
    timeout: float | None = None,
    resolver: Any | None = None,
) -> TextEncoder:
    """Build and return a text encoder.

    Model selection:
    - When *resolver* has an ``embedding`` task default configured (Model
      Providers UI), its provider/model/endpoint is used. Reloading the
      registry (``/admin/model-providers/reload``) picks up changes without a
      restart.
    - Otherwise the environment ``embedding_*`` settings apply:
        - If ``embedding_provider`` is explicitly set, use it.
        - Otherwise default to ``ollama`` in production and
          ``deterministic-test`` in dev/test.

    Production safety:
    - ``APP_ENV=prod`` rejects the ``deterministic-test`` provider unless
      ``EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD`` is explicitly set.

    Raises:
        RuntimeError: when the configured provider is not allowed in the
            current environment.
        ValueError: when the configured provider is unknown.
    """
    resolution = resolver.resolve("embedding") if resolver is not None and resolver.loaded else None
    if resolution is not None and resolution.model_name:
        base_url = resolution.base_url or settings.embedding_url or settings.ollama_url
        eff_timeout = timeout if timeout is not None else settings.embedding_timeout
        dimension = _resolution_dimension(resolution, settings)
        if resolution.provider_type == "ollama":
            return OllamaEmbeddingEncoder(
                base_url=base_url,
                model=resolution.model_name,
                dimension=dimension,
                max_tokens=settings.embedding_max_tokens,
                timeout=eff_timeout,
            )
        return OpenAICompatibleEmbeddingEncoder(
            base_url=base_url,
            model=resolution.model_name,
            dimension=dimension,
            api_key=resolution.api_key or settings.embedding_api_key,
            timeout=eff_timeout,
        )

    provider = settings.embedding_provider
    if not provider:
        provider = "ollama" if settings.app_env == "prod" else "deterministic-test"

    if provider == "deterministic-test":
        if settings.app_env == "prod" and not settings.embedding_provider_unsafe_allow_test_in_prod:
            raise RuntimeError(
                "Deterministic test encoder is not allowed in production. "
                "Set EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD=1 only if you "
                "explicitly understand the risks."
            )
        return DeterministicTestEncoder()

    if provider == "ollama":
        base_url = settings.embedding_url or settings.ollama_url
        return OllamaEmbeddingEncoder(
            base_url=base_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            max_tokens=settings.embedding_max_tokens,
            timeout=timeout if timeout is not None else settings.embedding_timeout,
        )

    if provider == "openai-compatible":
        if not settings.embedding_url:
            raise ValueError(
                "EMBEDDING_URL must be set when embedding_provider is 'openai-compatible'"
            )
        return OpenAICompatibleEmbeddingEncoder(
            base_url=settings.embedding_url,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
            api_key=settings.embedding_api_key,
            timeout=timeout if timeout is not None else settings.embedding_timeout,
        )

    raise ValueError(f"Unknown embedding provider: {provider}")


def build_reranker(
    settings: Settings,
    *,
    llm_provider: Any | None = None,
    resolver: Any | None = None,
) -> SearchReranker:
    """Build and return a search reranker based on *settings*.

    Resolution order:
    1. If ``search_reranker_enabled`` is False, return NoOpSearchReranker.
    2. If ``search_reranker_url`` is set, use the endpoint-based reranker
       (preferred — calls a dedicated cross-encoder service).
    3. Otherwise, fall back to the LLM-based (Ollama prompt) reranker.
       Requires *llm_provider* to be passed in.

    When *resolver* has a ``reranking`` task default, its model name overrides
    the environment reranker model (consistent with the chat reranker path).
    """
    resolution = resolver.resolve("reranking") if resolver is not None and resolver.loaded else None
    resolved_model = resolution.model_name if resolution is not None else None

    if not settings.search_reranker_enabled:
        return NoOpSearchReranker()

    if settings.search_reranker_url:
        return EndpointSearchReranker(
            url=settings.search_reranker_url,
            model=resolved_model or settings.search_reranker_model,
            min_score=settings.search_reranker_min_score,
            top_n=settings.search_reranker_depth,
            timeout=settings.search_reranker_timeout,
        )

    # LLM-based fallback: requires the Ollama client from app state.
    if llm_provider is None:
        logger.warning(
            "Search reranker enabled but no reranker_url and no llm_provider "
            "— falling back to NoOpSearchReranker"
        )
        return NoOpSearchReranker()

    return LLMSearchReranker(
        llm_provider=llm_provider,
        min_score=settings.search_reranker_min_score,
        top_n=settings.search_reranker_depth,
        model=resolved_model or settings.effective_reranker_model,
    )
