"""Asymmetric query/document embedding-prefix behaviour.

Instruction-tuned embedding models expect a short task/role prefix on the query
side (and, for some models, the document side). ``encode_query`` /
``encode_documents`` apply the configured prefixes; the raw ``encode`` /
``encode_batch`` primitives never do. Defaults are empty, so the asymmetric
helpers are byte-for-byte equivalent to the raw primitives until a prefix is set.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.search.encoder import (
    DeterministicTestEncoder,
    OllamaEmbeddingEncoder,
    OpenAICompatibleEmbeddingEncoder,
)


def _ollama_response(json_data: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = json_data
    response.raise_for_status = lambda: None
    return response


def _openai_response(json_data: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = json_data
    response.raise_for_status = lambda: None
    return response


class TestOllamaPrefixes:
    @patch("services.search.encoder.httpx.post")
    def test_encode_query_applies_query_prefix(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _ollama_response({"embeddings": [[0.1, 0.2]]})
        encoder = OllamaEmbeddingEncoder("http://ollama:11434", query_prefix="Q: ")

        encoder.encode_query("hello")

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["input"] == ["Q: hello"]

    @patch("services.search.encoder.httpx.post")
    def test_encode_documents_applies_document_prefix(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _ollama_response({"embeddings": [[0.1], [0.2]]})
        encoder = OllamaEmbeddingEncoder("http://ollama:11434", document_prefix="D: ")

        encoder.encode_documents(["a", "b"])

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["input"] == ["D: a", "D: b"]

    @patch("services.search.encoder.httpx.post")
    def test_query_prefix_not_applied_to_documents(self, mock_post: MagicMock) -> None:
        """A query-only prefix (the qwen3 case) must leave passages untouched."""
        mock_post.return_value = _ollama_response({"embeddings": [[0.1]]})
        encoder = OllamaEmbeddingEncoder("http://ollama:11434", query_prefix="Instruct: x\nQuery: ")

        encoder.encode_documents(["doc text"])

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["input"] == ["doc text"]

    @patch("services.search.encoder.httpx.post")
    def test_no_prefix_by_default_matches_raw_encode(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _ollama_response({"embeddings": [[0.1, 0.2]]})
        encoder = OllamaEmbeddingEncoder("http://ollama:11434")

        encoder.encode_query("hello")
        _, query_kwargs = mock_post.call_args
        encoder.encode_documents(["hello"])
        _, doc_kwargs = mock_post.call_args

        assert query_kwargs["json"]["input"] == ["hello"]
        assert doc_kwargs["json"]["input"] == ["hello"]


class TestOpenAICompatiblePrefixes:
    @patch("services.search.encoder.httpx.post")
    def test_encode_query_applies_query_prefix(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _openai_response({"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://proxy:8000", model="m", query_prefix="query: "
        )

        encoder.encode_query("hello")

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["input"] == ["query: hello"]

    @patch("services.search.encoder.httpx.post")
    def test_encode_documents_applies_document_prefix(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _openai_response(
            {
                "data": [
                    {"index": 0, "embedding": [0.1]},
                    {"index": 1, "embedding": [0.2]},
                ]
            }
        )
        encoder = OpenAICompatibleEmbeddingEncoder(
            "http://proxy:8000", model="m", document_prefix="passage: "
        )

        encoder.encode_documents(["a", "b"])

        _, kwargs = mock_post.call_args
        assert kwargs["json"]["input"] == ["passage: a", "passage: b"]


class TestDeterministicEncoderPrefixes:
    def test_query_equals_raw_encode_without_prefix(self) -> None:
        encoder = DeterministicTestEncoder()

        assert encoder.encode_query("hello") == encoder.encode("hello")
        assert encoder.encode_documents(["hello"]) == encoder.encode_batch(["hello"])
