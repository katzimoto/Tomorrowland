"""Tests for LLMProvider protocol, OpenAICompatibleLLMProvider, and build_llm_provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.intelligence.factory import build_llm_provider
from services.intelligence.llm_provider import (
    OpenAICompatibleLLMProvider,
    parse_json_array,
)
from services.intelligence.ollama_client import OllamaClient
from shared.config import Settings

# ---------------------------------------------------------------------------
# parse_json_array
# ---------------------------------------------------------------------------


def test_parse_json_array_clean_json() -> None:
    result = parse_json_array('["a", "b", "c"]')
    assert result == ["a", "b", "c"]


def test_parse_json_array_embedded_in_text() -> None:
    result = parse_json_array('Here are tags: ["finance", "contracts", "Q3"]')
    assert result == ["finance", "contracts", "Q3"]


def test_parse_json_array_no_array() -> None:
    assert parse_json_array("no array here") == []


def test_parse_json_array_malformed() -> None:
    assert parse_json_array("[broken json") == []


def test_parse_json_array_empty_array() -> None:
    assert parse_json_array("[]") == []


# ---------------------------------------------------------------------------
# OllamaClient satisfies LLMProvider (structural check)
# ---------------------------------------------------------------------------


def test_ollama_client_satisfies_llm_provider() -> None:
    """OllamaClient must be structurally compatible with LLMProvider."""
    import inspect

    client = OllamaClient(base_url="http://localhost:11434", model="mistral")
    assert hasattr(client, "model")
    assert hasattr(client, "generate")
    assert hasattr(client, "generate_stream")
    assert inspect.ismethod(client.generate)
    assert inspect.ismethod(client.generate_stream)


# ---------------------------------------------------------------------------
# OpenAICompatibleLLMProvider
# ---------------------------------------------------------------------------


def _make_httpx_response(content: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    resp.raise_for_status = MagicMock()
    return resp


def test_openai_compatible_generate_returns_content() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="lm-studio")
    mock_resp = _make_httpx_response("Paris")

    with patch("services.intelligence.llm_provider.httpx.post", return_value=mock_resp) as m:
        result = provider.generate("What is the capital of France?")

    assert result == "Paris"
    m.assert_called_once()
    call_kwargs = m.call_args
    assert "/v1/chat/completions" in call_kwargs[0][0]
    payload = call_kwargs[1]["json"]
    assert payload["model"] == "lm-studio"
    assert payload["messages"][0]["role"] == "user"
    assert payload["stream"] is False


def test_openai_compatible_generate_model_override() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="default-model")
    mock_resp = _make_httpx_response("answer")

    with patch("services.intelligence.llm_provider.httpx.post", return_value=mock_resp) as m:
        provider.generate("prompt", model="override-model")

    payload = m.call_args[1]["json"]
    assert payload["model"] == "override-model"


def test_openai_compatible_generate_empty_choices() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    resp = MagicMock()
    resp.json.return_value = {"choices": []}
    resp.raise_for_status = MagicMock()

    with patch("services.intelligence.llm_provider.httpx.post", return_value=resp):
        result = provider.generate("prompt")

    assert result == ""


def test_openai_compatible_generate_stream_raises() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    with pytest.raises(NotImplementedError):
        provider.generate_stream("prompt")


def test_openai_compatible_model_property() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="my-model")
    assert provider.model == "my-model"


# ---------------------------------------------------------------------------
# build_llm_provider factory
# ---------------------------------------------------------------------------


def _settings(**kwargs: str) -> Settings:
    base = {
        "app_env": "dev",
        "ollama_url": "http://ollama:11434",
        "ollama_model": "mistral",
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_factory_default_returns_ollama_client() -> None:
    settings = _settings()
    provider = build_llm_provider(settings)
    assert isinstance(provider, OllamaClient)
    assert provider.model == "mistral"


def test_factory_explicit_ollama_returns_ollama_client() -> None:
    settings = _settings(llm_provider="ollama")
    provider = build_llm_provider(settings)
    assert isinstance(provider, OllamaClient)


def test_factory_openai_compatible_returns_correct_provider() -> None:
    settings = _settings(llm_provider="openai-compatible")
    provider = build_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.model == "mistral"


def test_factory_llm_base_url_overrides_ollama_url() -> None:
    settings = _settings(llm_provider="ollama", llm_base_url="http://custom:11434")
    provider = build_llm_provider(settings)
    assert isinstance(provider, OllamaClient)
    # OllamaClient stores base_url with trailing slash stripped
    assert provider._base_url == "http://custom:11434"  # type: ignore[attr-defined]


def test_factory_llm_model_overrides_ollama_model() -> None:
    settings = _settings(llm_provider="ollama", llm_model="llama3")
    provider = build_llm_provider(settings)
    assert provider.model == "llama3"


def test_factory_openai_compatible_uses_llm_base_url() -> None:
    settings = _settings(
        llm_provider="openai-compatible",
        llm_base_url="http://lm-studio:1234",
        llm_model="local-model",
    )
    provider = build_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.model == "local-model"
    assert provider._base_url == "http://lm-studio:1234"  # type: ignore[attr-defined]


def test_factory_unknown_provider_raises() -> None:
    settings = _settings(llm_provider="unknown-provider")
    with pytest.raises(ValueError, match="unknown-provider"):
        build_llm_provider(settings)
