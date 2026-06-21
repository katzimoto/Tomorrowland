"""Vector-store quantization + search-param wiring for QdrantSearchClient (#826)."""

from __future__ import annotations

from unittest.mock import MagicMock

from qdrant_client.models import (
    BinaryQuantization,
    ScalarQuantization,
    ScalarType,
)

from services.search.qdrant import QdrantSearchClient
from shared.config import Settings


def _client(**kwargs: object) -> tuple[QdrantSearchClient, MagicMock]:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384, **kwargs)  # type: ignore[arg-type]
    mock = MagicMock()
    mock.collection_exists.return_value = False
    client._client = mock
    return client, mock


class TestQuantizationConfig:
    def test_default_has_no_quantization(self) -> None:
        client, mock = _client()
        client.create_collection_if_not_exists()
        kwargs = mock.create_collection.call_args.kwargs
        # Behaviour preserved: no quantization config passed when disabled.
        assert kwargs["quantization_config"] is None

    def test_scalar_quantization_config(self) -> None:
        client, mock = _client(quantization="scalar")
        client.create_collection_if_not_exists()
        qc = mock.create_collection.call_args.kwargs["quantization_config"]
        assert isinstance(qc, ScalarQuantization)
        assert qc.scalar.type == ScalarType.INT8
        assert qc.scalar.always_ram is True

    def test_binary_quantization_config(self) -> None:
        client, mock = _client(quantization="binary")
        client.create_collection_if_not_exists()
        qc = mock.create_collection.call_args.kwargs["quantization_config"]
        assert isinstance(qc, BinaryQuantization)


class TestSearchParams:
    def test_no_search_params_by_default(self) -> None:
        client, mock = _client()
        mock.collection_exists.return_value = True
        mock.query_points.return_value = MagicMock(points=[])
        client.search(vector=[0.1] * 384, group_ids=["g"])
        assert mock.query_points.call_args.kwargs["search_params"] is None

    def test_search_params_when_quantized(self) -> None:
        client, mock = _client(quantization="scalar", search_oversampling=3.0)
        mock.collection_exists.return_value = True
        mock.query_points.return_value = MagicMock(points=[])
        client.search(vector=[0.1] * 384, group_ids=["g"])
        params = mock.query_points.call_args.kwargs["search_params"]
        assert params is not None
        assert params.quantization.rescore is True
        assert params.quantization.oversampling == 3.0

    def test_search_filtered_passes_params(self) -> None:
        client, mock = _client(quantization="binary")
        mock.collection_exists.return_value = True
        mock.query_points.return_value = MagicMock(points=[])
        client.search_filtered(vector=[0.1] * 384, query_filter=None)
        assert mock.query_points.call_args.kwargs["search_params"] is not None


class TestFromSettings:
    def test_resolves_tuning_from_settings(self) -> None:
        settings = Settings(
            qdrant_url="http://qdrant:6333",
            qdrant_quantization="scalar",
            qdrant_search_rescore=False,
            qdrant_search_oversampling=4.0,
        )
        client = QdrantSearchClient.from_settings(settings, dimension=768)
        assert client.dimension == 768
        assert client._quantization == "scalar"
        assert client._search_rescore is False
        assert client._search_oversampling == 4.0

    def test_defaults_preserve_behaviour(self) -> None:
        settings = Settings(qdrant_url="http://qdrant:6333")
        client = QdrantSearchClient.from_settings(settings, dimension=384)
        assert client._quantization == ""
        assert client._quantization_config() is None
        assert client._search_params() is None
