from __future__ import annotations

from shared.config import Settings

from .encoder import DeterministicTestEncoder, OllamaEmbeddingEncoder, TextEncoder


def build_encoder(
    settings: Settings,
) -> TextEncoder:
    """Build and return a text encoder based on *settings*.

    Provider resolution:
    - If ``embedding_provider`` is explicitly set, use it.
    - Otherwise default to ``ollama`` in production and ``deterministic-test``
      in dev/test.

    Production safety:
    - ``APP_ENV=prod`` rejects the ``deterministic-test`` provider unless
      ``EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD`` is explicitly set.

    Raises:
        RuntimeError: when the configured provider is not allowed in the
            current environment.
        ValueError: when the configured provider is unknown.
    """
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
        )

    raise ValueError(f"Unknown embedding provider: {provider}")
