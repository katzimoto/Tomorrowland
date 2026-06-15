from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.intelligence.ollama_client import OllamaClient


def test_generate_success() -> None:
    client = OllamaClient(base_url="http://ollama:11434", model="mistral")
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Generated text"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = client.generate("Test prompt")
        assert result == "Generated text"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"]["model"] == "mistral"
        assert call_args[1]["json"]["prompt"] == "Test prompt"
        assert call_args[1]["json"]["stream"] is False


def test_generate_with_custom_model() -> None:
    client = OllamaClient(base_url="http://ollama:11434", model="mistral")
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Custom model output"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_response) as mock_post:
        result = client.generate("Test prompt", model="llama3")
        assert result == "Custom model output"
        assert mock_post.call_args[1]["json"]["model"] == "llama3"


def test_generate_http_error() -> None:
    client = OllamaClient(base_url="http://ollama:11434")
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503",
        request=MagicMock(),
        response=MagicMock(status_code=503),
    )

    with patch("httpx.post", return_value=mock_response), pytest.raises(httpx.HTTPStatusError):
        client.generate("Test prompt")


def test_parse_json_array_valid() -> None:
    text = 'Some text before [{"name": "Alice", "type": "person"}] and after'
    result = OllamaClient.parse_json_array(text)
    assert result == [{"name": "Alice", "type": "person"}]


def test_parse_json_array_with_markdown_fences() -> None:
    text = """Here are the entities:
```json
[{"name": "Bob", "type": "organization"}]
```
"""
    result = OllamaClient.parse_json_array(text)
    assert result == [{"name": "Bob", "type": "organization"}]


def test_parse_json_array_invalid_json() -> None:
    text = "No array here"
    result = OllamaClient.parse_json_array(text)
    assert result == []


def test_parse_json_array_malformed_json() -> None:
    text = "[{invalid json}]"
    result = OllamaClient.parse_json_array(text)
    assert result == []
