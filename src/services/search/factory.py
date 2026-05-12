from __future__ import annotations

from typing import Literal

from shared.config import Settings

from .encoder import DeterministicTestEncoder, TextEncoder


def build_encoder(
    settings: Settings,
) -> TextEncoder:
    """Build and return a text encoder based on *settings*.

    Production safety:
    - ``APP_ENV=prod`` rejects the ``deterministic-test`` provider unless
      ``EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD`` is explicitly set.

    Raises:
        RuntimeError: when the configured provider is not allowed in the
            current environment.
        ValueError: when the configured provider is unknown.
    """
    provider: Literal["deterministic-test"] | str = settings.embedding_provider

    if provider == "deterministic-test":
        if settings.app_env == "prod" and not settings.embedding_provider_unsafe_allow_test_in_prod:
            raise RuntimeError(
                "Deterministic test encoder is not allowed in production. "
                "Set EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD=1 only if you "
                "explicitly understand the risks."
            )
        return DeterministicTestEncoder()

    raise ValueError(f"Unknown embedding provider: {provider}")
