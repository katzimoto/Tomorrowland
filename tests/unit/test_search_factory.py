from __future__ import annotations

import pytest

from services.intelligence.task_defaults import TaskResolution
from services.search.encoder import (
    DeterministicTestEncoder,
    OllamaEmbeddingEncoder,
    OpenAICompatibleEmbeddingEncoder,
)
from services.search.factory import build_encoder, build_reranker
from services.search.reranker import EndpointSearchReranker, LLMSearchReranker
from shared.config import Settings


class _FakeResolver:
    """Minimal stand-in for TaskDefaultResolver in unit tests."""

    def __init__(self, resolutions: dict[str, TaskResolution], *, loaded: bool = True) -> None:
        self._resolutions = resolutions
        self.loaded = loaded

    def resolve(self, task_type: str) -> TaskResolution | None:
        return self._resolutions.get(task_type)


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
    assert encoder._model == "qwen3-embedding:8b"


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
# OpenAI-compatible embedding encoder
# ---------------------------------------------------------------------------


def test_factory_builds_openai_compatible_encoder() -> None:
    settings = Settings(
        app_env="dev",
        embedding_provider="openai-compatible",
        embedding_url="http://openai-proxy:8000",
        embedding_model="text-embedding-3-small",
        embedding_dimension=768,
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, OpenAICompatibleEmbeddingEncoder)
    assert encoder._base_url == "http://openai-proxy:8000"
    assert encoder._model == "text-embedding-3-small"
    assert encoder._dimension == 768


def test_factory_openai_compatible_requires_embedding_url() -> None:
    settings = Settings(
        app_env="dev",
        embedding_provider="openai-compatible",
        embedding_url="",
    )

    with pytest.raises(ValueError, match="EMBEDDING_URL must be set"):
        build_encoder(settings)


def test_factory_openai_compatible_forwards_api_key() -> None:
    settings = Settings(
        app_env="dev",
        embedding_provider="openai-compatible",
        embedding_url="http://openai-proxy:8000",
        embedding_api_key="sk-test-key",
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, OpenAICompatibleEmbeddingEncoder)
    assert encoder._api_key == "sk-test-key"


def test_factory_openai_compatible_empty_api_key() -> None:
    settings = Settings(
        app_env="dev",
        embedding_provider="openai-compatible",
        embedding_url="http://openai-proxy:8000",
        embedding_api_key="",
    )
    encoder = build_encoder(settings)

    assert isinstance(encoder, OpenAICompatibleEmbeddingEncoder)
    assert encoder._api_key == ""


def test_factory_openai_compatible_timeout_override() -> None:
    settings = Settings(
        app_env="dev",
        embedding_provider="openai-compatible",
        embedding_url="http://openai-proxy:8000",
        embedding_timeout=180.0,
    )
    encoder = build_encoder(settings, timeout=5.0)

    assert isinstance(encoder, OpenAICompatibleEmbeddingEncoder)
    assert encoder._timeout == 5.0


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


# ---------------------------------------------------------------------------
# Resolver-driven model selection (Model Providers registry)
# ---------------------------------------------------------------------------


def test_embedding_task_default_overrides_env_model() -> None:
    settings = Settings(_env_file=None, app_env="dev", embedding_model="env-model")
    resolver = _FakeResolver(
        {
            "embedding": TaskResolution(
                provider_name="local",
                provider_type="ollama",
                model_name="registry-embed",
                base_url="http://prov:11434",
                parameters={"dimension": 1024},
            )
        }
    )
    encoder = build_encoder(settings, resolver=resolver)

    assert isinstance(encoder, OllamaEmbeddingEncoder)
    assert encoder._model == "registry-embed"
    assert encoder._base_url == "http://prov:11434"
    assert encoder._dimension == 1024


def test_embedding_openai_compatible_task_default() -> None:
    settings = Settings(_env_file=None, app_env="dev")
    resolver = _FakeResolver(
        {
            "embedding": TaskResolution(
                provider_name="proxy",
                provider_type="openai-compatible",
                model_name="text-embedding-3-small",
                base_url="http://proxy:8000",
                api_key="sk-x",
            )
        }
    )
    encoder = build_encoder(settings, resolver=resolver)

    assert isinstance(encoder, OpenAICompatibleEmbeddingEncoder)
    assert encoder._model == "text-embedding-3-small"
    assert encoder._api_key == "sk-x"


def test_embedding_falls_back_to_env_when_resolver_unloaded() -> None:
    settings = Settings(_env_file=None, app_env="dev", embedding_provider="deterministic-test")
    resolver = _FakeResolver({"embedding": TaskResolution("p", "ollama", "x")}, loaded=False)
    encoder = build_encoder(settings, resolver=resolver)

    assert isinstance(encoder, DeterministicTestEncoder)


def test_reranking_task_default_overrides_endpoint_model() -> None:
    settings = Settings(
        _env_file=None,
        search_reranker_enabled=True,
        search_reranker_url="http://rerank:8080",
        search_reranker_model="env-rerank",
    )
    resolver = _FakeResolver(
        {"reranking": TaskResolution("p", "openai-compatible", "registry-rerank")}
    )
    reranker = build_reranker(settings, resolver=resolver)

    assert isinstance(reranker, EndpointSearchReranker)
    assert reranker._model == "registry-rerank"


def test_reranking_task_default_overrides_llm_model() -> None:
    settings = Settings(_env_file=None, search_reranker_enabled=True, search_reranker_url="")
    resolver = _FakeResolver({"reranking": TaskResolution("p", "ollama", "registry-rerank")})
    reranker = build_reranker(settings, llm_provider=object(), resolver=resolver)

    assert isinstance(reranker, LLMSearchReranker)
    assert reranker._model == "registry-rerank"
