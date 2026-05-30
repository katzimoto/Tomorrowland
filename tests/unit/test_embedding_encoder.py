from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.search.encoder import OpenAICompatibleEmbeddingEncoder


class TestOpenAICompatibleEmbeddingEncoder:
    """Unit tests for OpenAICompatibleEmbeddingEncoder with mocked HTTP."""

    def test_dimension_property(self) -> None:
        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small", dimension=768
        )
        assert encoder.dimension == 768

    @patch("services.search.encoder.httpx.post")
    def test_encode_hits_v1_embeddings(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response(
            {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )
        vec = encoder.encode("hello")

        assert vec == [0.1, 0.2, 0.3]
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://embeddings:8000/v1/embeddings"

    @patch("services.search.encoder.httpx.post")
    def test_encode_batch_returns_vectors(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response(
            {
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ]
            }
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )
        vectors = encoder.encode_batch(["hello", "world"])

        assert len(vectors) == 2
        assert vectors[0] == [0.1, 0.2]
        assert vectors[1] == [0.3, 0.4]

    @patch("services.search.encoder.httpx.post")
    def test_encode_batch_empty_list(self, mock_post: MagicMock) -> None:
        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )
        vectors = encoder.encode_batch([])

        assert vectors == []
        mock_post.assert_not_called()

    @patch("services.search.encoder.httpx.post")
    def test_encode_rejects_non_string(self, mock_post: MagicMock) -> None:
        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )

        with pytest.raises(TypeError, match="text must be a string"):
            encoder.encode(123)  # type: ignore[arg-type]

        mock_post.assert_not_called()

    @patch("services.search.encoder.httpx.post")
    def test_auth_header_present_when_api_key_set(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response(
            {"data": [{"index": 0, "embedding": [0.1]}]}
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000",
            model="text-embedding-3-small",
            api_key="sk-test-key",
        )
        encoder.encode("hello")

        _, kwargs = mock_post.call_args
        headers = kwargs["headers"]
        assert headers.get("Authorization") == "Bearer sk-test-key"

    @patch("services.search.encoder.httpx.post")
    def test_auth_header_absent_when_api_key_empty(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response(
            {"data": [{"index": 0, "embedding": [0.1]}]}
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000",
            model="text-embedding-3-small",
            api_key="",
        )
        encoder.encode("hello")

        _, kwargs = mock_post.call_args
        headers = kwargs.get("headers", {})
        assert "Authorization" not in headers

    @patch("services.search.encoder.httpx.post")
    def test_encode_batch_preserves_order_when_shuffled(
        self, mock_post: MagicMock
    ) -> None:
        """Batch results must be sorted by index so the return order matches
        the input order even when the server returns shuffled data."""
        mock_post.return_value = _response(
            {
                "data": [
                    {"index": 2, "embedding": [0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ]
            }
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )
        vectors = encoder.encode_batch(["a", "b", "c"])

        assert vectors[0] == [0.1, 0.2]
        assert vectors[1] == [0.3, 0.4]
        assert vectors[2] == [0.5, 0.6]

    @patch("services.search.encoder.httpx.post")
    def test_encode_request_payload(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response(
            {"data": [{"index": 0, "embedding": [0.1]}]}
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )
        encoder.encode_batch(["hello", "world"])

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["model"] == "text-embedding-3-small"
        assert kwargs["json"]["input"] == ["hello", "world"]

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_http_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response({}, status_code=500)
        mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_post.return_value,
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )

        with pytest.raises(httpx.HTTPStatusError):
            encoder.encode("hello")

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_missing_data_key(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response({"object": "list"})

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )

        with pytest.raises(RuntimeError, match="missing 'data' key"):
            encoder.encode("hello")

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_missing_embedding_in_entry(
        self, mock_post: MagicMock
    ) -> None:
        mock_post.return_value = _response(
            {"data": [{"index": 0, "embedding": None}]}
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )

        with pytest.raises(RuntimeError, match="missing 'embedding'"):
            encoder.encode("hello")

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_connect_error(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )

        with pytest.raises(RuntimeError, match="Cannot connect"):
            encoder.encode("hello")

    @patch("services.search.encoder.httpx.post")
    def test_encode_raises_on_timeout(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = httpx.TimeoutException("Timed out")

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )

        with pytest.raises(RuntimeError, match="timed out"):
            encoder.encode("hello")

    @patch("services.search.encoder.httpx.post")
    def test_content_type_header(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _response(
            {"data": [{"index": 0, "embedding": [0.1]}]}
        )

        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://embeddings:8000", model="text-embedding-3-small"
        )
        encoder.encode("hello")

        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["Content-Type"] == "application/json"


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
