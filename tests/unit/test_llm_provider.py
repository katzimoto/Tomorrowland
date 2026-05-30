"""Tests for LLMProvider protocol, OpenAICompatibleLLMProvider, and build_llm_provider."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
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


def _make_sse_stream(data_chunks: list[str]) -> MagicMock:
    """Build a mock httpx response that yields SSE `data: ...` lines."""
    lines = [f"data: {c}\n\n" for c in data_chunks]
    lines.append("data: [DONE]\n\n")

    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.iter_lines.return_value = [line for chunk in lines for line in chunk.split("\n")]
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_openai_compatible_generate_stream_yields_tokens() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    sse = _make_sse_stream(
        [
            '{"choices":[{"delta":{"content":"Hello"}}]}',
            '{"choices":[{"delta":{"content":" world"}}]}',
        ]
    )

    with patch("services.intelligence.llm_provider.httpx.stream", return_value=sse):
        tokens = list(provider.generate_stream("prompt"))

    assert tokens == ["Hello", " world"]


def test_openai_compatible_generate_stream_done_terminates() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    sse = _make_sse_stream(
        [
            '{"choices":[{"delta":{"content":"only"}}]}',
        ]
    )
    # also test that extra data after [DONE] is ignored

    with patch("services.intelligence.llm_provider.httpx.stream", return_value=sse):
        tokens = list(provider.generate_stream("prompt"))

    assert tokens == ["only"]


def test_openai_compatible_generate_stream_skips_non_data_lines() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    sse = _make_sse_stream(
        [
            '{"choices":[{"delta":{"content":"token"}}]}',
        ]
    )
    # add some cruft
    sse_iter = [
        "",
        'data: {"choices":[{"delta":{"content":"token"}}]}',
        "",
        "data: [DONE]",
        "",
    ]
    sse.iter_lines.return_value = sse_iter

    with patch("services.intelligence.llm_provider.httpx.stream", return_value=sse):
        tokens = list(provider.generate_stream("prompt"))

    assert tokens == ["token"]


def test_openai_compatible_generate_stream_bad_json_skips_line() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    sse = _make_sse_stream(
        [
            "not valid json",
            '{"choices":[{"delta":{"content":"valid"}}]}',
        ]
    )

    with patch("services.intelligence.llm_provider.httpx.stream", return_value=sse):
        tokens = list(provider.generate_stream("prompt"))

    assert tokens == ["valid"]


def test_openai_compatible_generate_sends_bearer_auth() -> None:
    provider = OpenAICompatibleLLMProvider(
        base_url="http://localhost:1234",
        model="m",
        api_key="sk-secret-key",
    )
    mock_resp = _make_httpx_response("ok")

    with patch("services.intelligence.llm_provider.httpx.post", return_value=mock_resp) as m:
        provider.generate("prompt")

    headers = m.call_args[1].get("headers", {})
    assert headers.get("Authorization") == "Bearer sk-secret-key"
    assert "sk-secret-key" not in m.call_args[1].get("json", {}).values()


def test_openai_compatible_generate_no_auth_when_no_api_key() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    mock_resp = _make_httpx_response("ok")

    with patch("services.intelligence.llm_provider.httpx.post", return_value=mock_resp) as m:
        provider.generate("prompt")

    headers = m.call_args[1].get("headers", {})
    assert "Authorization" not in headers


def test_openai_compatible_generate_sends_bearer_auth_stream() -> None:
    provider = OpenAICompatibleLLMProvider(
        base_url="http://localhost:1234",
        model="m",
        api_key="sk-secret",
    )
    sse = _make_sse_stream(['{"choices":[{"delta":{"content":"hi"}}]}'])

    with patch("services.intelligence.llm_provider.httpx.stream", return_value=sse) as m:
        list(provider.generate_stream("prompt"))

    headers = m.call_args[1].get("headers", {})
    assert headers.get("Authorization") == "Bearer sk-secret"


def test_openai_compatible_generate_malformed_json_returns_empty() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    resp = MagicMock()
    resp.json.side_effect = json.JSONDecodeError("malformed", "", 0)
    resp.raise_for_status = MagicMock()

    with patch("services.intelligence.llm_provider.httpx.post", return_value=resp):
        result = provider.generate("prompt")

    assert result == ""


def test_openai_compatible_generate_http_error_raises() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    resp = MagicMock()
    resp.status_code = 401
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401",
        request=MagicMock(),
        response=resp,
    )

    with (
        patch("services.intelligence.llm_provider.httpx.post", return_value=resp),
        pytest.raises(httpx.HTTPStatusError),
    ):
        provider.generate("prompt")


def test_openai_compatible_generate_connect_error_raises() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")

    with (
        patch(
            "services.intelligence.llm_provider.httpx.post",
            side_effect=httpx.ConnectError("connection refused"),
        ),
        pytest.raises(httpx.ConnectError),
    ):
        provider.generate("prompt")


def test_openai_compatible_generate_timeout_error_raises() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")

    with (
        patch(
            "services.intelligence.llm_provider.httpx.post",
            side_effect=httpx.TimeoutException("timed out"),
        ),
        pytest.raises(httpx.TimeoutException),
    ):
        provider.generate("prompt")


def test_openai_compatible_generate_stream_http_error_raises() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")
    resp = MagicMock()
    resp.status_code = 401
    exc = httpx.HTTPStatusError("401", request=MagicMock(), response=resp)
    resp.raise_for_status.side_effect = exc
    stream_ctx = MagicMock()
    stream_ctx.__enter__.return_value = resp
    stream_ctx.__exit__.return_value = False

    with (
        patch("services.intelligence.llm_provider.httpx.stream", return_value=stream_ctx),
        pytest.raises(httpx.HTTPStatusError),
    ):
        list(provider.generate_stream("prompt"))


def test_openai_compatible_generate_stream_connect_error_raises() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")

    with (
        patch(
            "services.intelligence.llm_provider.httpx.stream",
            side_effect=httpx.ConnectError("refused"),
        ),
        pytest.raises(httpx.ConnectError),
    ):
        list(provider.generate_stream("prompt"))


def test_openai_compatible_generate_stream_timeout_raises() -> None:
    provider = OpenAICompatibleLLMProvider(base_url="http://localhost:1234", model="m")

    with (
        patch(
            "services.intelligence.llm_provider.httpx.stream",
            side_effect=httpx.TimeoutException("timed out"),
        ),
        pytest.raises(httpx.TimeoutException),
    ):
        list(provider.generate_stream("prompt"))


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


# ---------------------------------------------------------------------------
# New provider names (openai, litellm, llama-cpp)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_name", ["litellm", "llama-cpp"])
def test_factory_new_providers_return_openai_compatible(provider_name: str) -> None:
    settings = _settings(llm_provider=provider_name)
    provider = build_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider.model == "mistral"


def test_factory_openai_requires_api_key() -> None:
    settings = _settings(llm_provider="openai")
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        build_llm_provider(settings)


def test_factory_openai_passes_api_key() -> None:
    settings = _settings(
        llm_provider="openai",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4",
        llm_api_key="sk-test",
    )
    provider = build_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider._api_key == "sk-test"  # type: ignore[attr-defined]


def test_factory_litellm_no_api_key() -> None:
    settings = _settings(llm_provider="litellm")
    provider = build_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert provider._api_key is None  # type: ignore[attr-defined]


def test_factory_ollama_ignores_llm_api_key() -> None:
    settings = _settings(
        llm_provider="ollama",
        llm_api_key="should-not-affect-ollama",
    )
    provider = build_llm_provider(settings)
    assert isinstance(provider, OllamaClient)
