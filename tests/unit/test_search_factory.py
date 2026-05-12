from __future__ import annotations

import pytest

from services.search.encoder import DeterministicTestEncoder
from services.search.factory import build_encoder
from shared.config import Settings


def test_factory_builds_deterministic_test_encoder() -> None:
    settings = Settings(app_env="dev", embedding_provider="deterministic-test")
    encoder = build_encoder(settings)

    assert isinstance(encoder, DeterministicTestEncoder)
    vec = encoder.encode("hello")
    assert len(vec) == 384


def test_factory_blocks_deterministic_test_in_prod() -> None:
    settings = Settings(app_env="prod", embedding_provider="deterministic-test")

    with pytest.raises(RuntimeError, match="not allowed in production"):
        build_encoder(settings)


def test_factory_allows_deterministic_test_in_prod_with_unsafe_override() -> None:
    settings = Settings(
        app_env="prod",
        embedding_provider="deterministic-test",
        embedding_provider_unsafe_allow_test_in_prod=True,
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, DeterministicTestEncoder)


def test_factory_rejects_unknown_provider() -> None:
    settings = Settings(app_env="dev", embedding_provider="unknown-provider")

    with pytest.raises(ValueError, match="Unknown embedding provider"):
        build_encoder(settings)
