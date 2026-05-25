from __future__ import annotations

import pytest

from services.search.encoder import DeterministicTestEncoder, OllamaEmbeddingEncoder
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


def test_factory_defaults_to_deterministic_test_in_dev() -> None:
    settings = Settings(app_env="dev", embedding_provider="")
    encoder = build_encoder(settings)

    assert isinstance(encoder, DeterministicTestEncoder)


def test_factory_defaults_to_deterministic_test_in_test() -> None:
    settings = Settings(app_env="test", embedding_provider="")
    encoder = build_encoder(settings)

    assert isinstance(encoder, DeterministicTestEncoder)


def test_factory_defaults_to_ollama_in_prod() -> None:
    settings = Settings(app_env="prod", embedding_provider="")
    encoder = build_encoder(settings)

    assert isinstance(encoder, OllamaEmbeddingEncoder)
    assert encoder._model == "nomic-embed-text"


def test_factory_builds_ollama_with_custom_model() -> None:
    settings = Settings(
        app_env="dev",
        embedding_provider="ollama",
        embedding_model="custom-model",
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, OllamaEmbeddingEncoder)
    assert encoder._model == "custom-model"


def test_factory_ollama_uses_embedding_url_when_set() -> None:
    settings = Settings(
        app_env="dev",
        embedding_provider="ollama",
        embedding_url="http://custom-ollama:11434",
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, OllamaEmbeddingEncoder)
    assert encoder._base_url == "http://custom-ollama:11434"


def test_factory_ollama_falls_back_to_ollama_url() -> None:
    # Suppress .env file loading so EMBEDDING_URL from the dev env file does
    # not shadow the ollama_url fallback being tested here.
    settings = Settings(
        _env_file=None,
        app_env="dev",
        embedding_provider="ollama",
        embedding_url="",
        ollama_url="http://fallback-ollama:11434",
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, OllamaEmbeddingEncoder)
    assert encoder._base_url == "http://fallback-ollama:11434"


# ---------------------------------------------------------------------------
# search_embedding_timeout — graceful degradation
# ---------------------------------------------------------------------------


def test_factory_timeout_override_applied() -> None:
    """build_encoder(timeout=N) produces an encoder with that timeout, not embedding_timeout."""
    settings = Settings(
        app_env="prod",
        embedding_provider="ollama",
        embedding_timeout=180.0,
    )
    encoder = build_encoder(settings, timeout=5.0)

    assert isinstance(encoder, OllamaEmbeddingEncoder)
    assert encoder._timeout == 5.0


def test_factory_uses_settings_timeout_when_override_absent() -> None:
    """When no override is given, embedding_timeout from settings is used."""
    settings = Settings(
        app_env="prod",
        embedding_provider="ollama",
        embedding_timeout=42.0,
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, OllamaEmbeddingEncoder)
    assert encoder._timeout == 42.0


def test_settings_search_embedding_timeout_default() -> None:
    """search_embedding_timeout default is 5 s — safely below nginx's 110 s read timeout."""
    settings = Settings()
    assert settings.search_embedding_timeout == 5.0


def test_settings_search_embedding_timeout_customisable() -> None:
    settings = Settings(search_embedding_timeout=10.0)
    assert settings.search_embedding_timeout == 10.0
