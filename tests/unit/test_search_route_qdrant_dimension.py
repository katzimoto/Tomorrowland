"""
Tests: /search fallback QdrantSearchClient must use the active encoder's dimension.

Regression for #758 — before the fix, the fallback was constructed with the
default dimension (384) regardless of the configured embedding model.
"""

from __future__ import annotations

import inspect

import pytest

from services.search.encoder import OllamaEmbeddingEncoder
from services.search.factory import build_encoder
from services.search.qdrant import QdrantSearchClient
from shared.config import Settings

# ---------------------------------------------------------------------------
# Source-level regression (fails before the fix, passes after)
# ---------------------------------------------------------------------------


def test_search_route_fallback_qdrant_passes_encoder_dimension() -> None:
    """search.py must pass dimension=encoder.dimension when constructing the fallback client."""
    from services.api.routers import search as search_module

    source = inspect.getsource(search_module)
    assert "dimension=encoder.dimension" in source, (
        "Fallback QdrantSearchClient in search.py must pass dimension=encoder.dimension. "
        "Without it, /search queries the wrong collection when the active encoder "
        "dimension differs from the QdrantSearchClient default (384)."
    )


# ---------------------------------------------------------------------------
# Behavioural: encoder.dimension flows through to QdrantSearchClient correctly
# ---------------------------------------------------------------------------


def test_deterministic_encoder_dimension_matches_default_qdrant_collection() -> None:
    """DeterministicTestEncoder (dim=384) → QdrantSearchClient uses tomorrowland_chunks_384."""
    settings = Settings(
        embedding_provider="deterministic-test",
        qdrant_url="http://qdrant:6333",
    )
    encoder = build_encoder(settings)
    client = QdrantSearchClient(url=settings.qdrant_url, dimension=encoder.dimension)

    assert client.dimension == encoder.dimension
    assert client.collection_name == f"tomorrowland_chunks_{encoder.dimension}"


@pytest.mark.parametrize("dim", [768, 1024, 4096])
def test_non_default_encoder_dimension_routes_to_correct_collection(dim: int) -> None:
    """Regression: non-default encoder dimension must produce the matching collection name.

    Before #758 the fallback used dimension=384 unconditionally, so a 768-dim
    (or any non-384-dim) encoder would query the wrong collection.
    """
    encoder = OllamaEmbeddingEncoder(
        base_url="http://ollama:11434",
        model="some-embed-model",
        dimension=dim,
    )
    client = QdrantSearchClient(url="http://qdrant:6333", dimension=encoder.dimension)

    assert client.dimension == dim
    assert client.collection_name == f"tomorrowland_chunks_{dim}"
    # Confirm it is NOT the old hard-wired default collection
    assert client.collection_name != "tomorrowland_chunks_384"


def test_openai_compatible_encoder_dimension_matches_qdrant_collection() -> None:
    """OpenAI-compatible encoder dimension must flow through to the qdrant client."""
    from services.search.encoder import OpenAICompatibleEmbeddingEncoder

    encoder = OpenAICompatibleEmbeddingEncoder(
        base_url="http://embed-svc:8080",
        model="text-embedding-3-small",
        dimension=1536,
    )
    client = QdrantSearchClient(url="http://qdrant:6333", dimension=encoder.dimension)

    assert client.dimension == 1536
    assert client.collection_name == "tomorrowland_chunks_1536"
