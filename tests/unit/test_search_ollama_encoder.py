from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.search.encoder import OllamaEmbeddingEncoder


class TestOllamaEmbeddingEncoder:
    """Unit tests for OllamaEmbeddingEncoder with mocked HTTP responses."""

    def test_dimension_property(self) -> None:
        encoder = OllamaEmbeddingEncoder("http://ollama:11434", dimension=512)
        assert encoder.dimension == 512

    @patch("services.search.encoder.httpx.post")
    def test_encode_returns_vector(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._response({"embeddings": [[0.1, 0.2, 0.3]]})

        encoder = OllamaEmbeddingEncoder("http://ollama:11434", model="test-model")
        vec = encoder.encode("hello")

        assert vec == [0.1, 0.2, 0.3]
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "test-model"
        assert kwargs["json"]["input"] == ["hello"]

    @patch("services.search.encoder.httpx.post")
    def test_encode_batch_returns_vectors(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._response({"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

        encoder = OllamaEmbeddingEncoder("http://ollama:11434")
        vectors = encoder.encode_batch(["hello", "world"])

        assert len(vectors) == 2
        assert vectors[0] == [0.1, 0.2]
        assert vectors[1] == [0.3, 0.4]

    @patch("services.search.encoder.httpx.post")
    def test_encode_batch_empty_list(self, mock_post: MagicMock) -> None:
        encoder = OllamaEmbeddingEncoder("http://ollama:11434")
        vectors = encoder.encode_batch([])

        assert vectors == []
        mock_post.assert_not_called()

    @patch("services.search.encoder.httpx.post")
    def test_encode_rejects_non_string(self, mock_post: MagicMock) -> None:
        encoder = OllamaEmbeddingEncoder("http://ollama:11434")

        with pytest.raises(TypeError, match="text must be a string"):
            encoder.encode(123)  # type: ignore[arg-type]

        mock_post.assert_not_called()

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_404_with_no_fallback(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._response({}, status_code=404)

        encoder = OllamaEmbeddingEncoder("http://ollama:11434")

        with pytest.raises(RuntimeError, match="does not support the /api/embed endpoint"):
            encoder.encode("hello")

        mock_post.assert_called_once()

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_missing_embeddings_key(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._response({"other": "data"})

        encoder = OllamaEmbeddingEncoder("http://ollama:11434")

        with pytest.raises(RuntimeError, match="missing 'embeddings' key"):
            encoder.encode("hello")

    @patch("services.search.encoder.httpx.post")
    def test_embed_sends_num_ctx_when_max_tokens_set(self, mock_post: MagicMock) -> None:
        """num_ctx must be pinned in options to override Modelfile defaults.

        nomic-embed-text ships with PARAMETER num_ctx 8192 in its Ollama
        Modelfile, but n_ctx_train=2048. Without an explicit options.num_ctx
        at request level, Ollama logs a warning and wastes KV-cache memory.
        """
        mock_post.return_value = self._response({"embeddings": [[0.1, 0.2]]})

        encoder = OllamaEmbeddingEncoder(
            "http://ollama:11434", model="nomic-embed-text", max_tokens=1024
        )
        encoder.encode("hello")

        _, kwargs = mock_post.call_args
        assert kwargs["json"].get("options", {}).get("num_ctx") == 1024

    @patch("services.search.encoder.httpx.post")
    def test_embed_omits_options_when_max_tokens_not_set(self, mock_post: MagicMock) -> None:
        """When no max_tokens is configured, options should not be injected."""
        mock_post.return_value = self._response({"embeddings": [[0.1, 0.2]]})

        encoder = OllamaEmbeddingEncoder("http://ollama:11434")
        encoder.encode("hello")

        _, kwargs = mock_post.call_args
        assert "options" not in kwargs["json"]

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_http_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = self._response({}, status_code=500)
        mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_post.return_value,
        )

        encoder = OllamaEmbeddingEncoder("http://ollama:11434")

        with pytest.raises(httpx.HTTPStatusError):
            encoder.encode("hello")

    @staticmethod
    def _response(json_data: dict, status_code: int = 200) -> MagicMock:
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data

        def _raise() -> None:
            if status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"{status_code} Error",
                    request=MagicMock(),
                    response=response,
                )

        response.raise_for_status = _raise
        return response
