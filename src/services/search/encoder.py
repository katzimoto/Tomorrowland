from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol

import httpx

DIMENSIONS = 384

logger = logging.getLogger(__name__)


class TextEncoder(Protocol):
    """Protocol for text-to-vector encoders."""

    def encode(self, text: str) -> list[float]:
        """Return a vector for *text*."""
        ...

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Return a list of vectors for *texts*."""
        ...


class DeterministicTestEncoder:
    """Deterministic test encoder that produces 384-dimensional vectors.

    Vectors are derived from the SHA-256 hash of the input text. This encoder
    has zero external dependencies (no torch, transformers, etc.) and is
    intended for use in tests and CI only. It must not be used in production
    without an explicit unsafe override.
    """

    def encode(self, text: str) -> list[float]:
        """Return a 384-dimensional vector for *text*."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
        vector: list[float] = []

        # Generate deterministic floats from hash bytes
        for i in range(DIMENSIONS):
            # Cycle through hash bytes if needed (SHA-256 is 32 bytes)
            byte_idx = i % len(hash_bytes)
            # Use a simple deterministic formula to produce a float in [-1, 1]
            val = (hash_bytes[byte_idx] / 255.0) * 2 - 1
            # Add variation using the index
            val += ((i * 31) % 100) / 10000.0
            # Clamp to [-1, 1]
            val = max(-1.0, min(1.0, val))
            vector.append(val)

        return vector

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Return a list of vectors for *texts*."""
        return [self.encode(text) for text in texts]


class OllamaEmbeddingEncoder:
    """Production encoder using Ollama's modern embedding endpoint.

    Calls the Ollama ``/api/embed`` endpoint for both single-text and batch
    embedding.  The legacy ``/api/embeddings`` endpoint is not used.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "nomic-embed-text",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def encode(self, text: str) -> list[float]:
        """Return a vector for *text* via Ollama."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        return self._embed_batch([text])[0]

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Return vectors for *texts* via Ollama."""
        if not texts:
            return []

        return self._embed_batch(texts)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Use the modern ``/api/embed`` endpoint."""
        url = f"{self._base_url}/api/embed"
        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }
        logger.debug(
            "Ollama embed model=%s batch_size=%d",
            self._model,
            len(texts),
        )
        response = httpx.post(url, json=payload, timeout=self._timeout)
        if response.status_code == 404:
            raise RuntimeError(
                f"Ollama model '{self._model}' does not support the /api/embed endpoint. "
                f"Update Ollama or use a model that supports the modern embedding API."
            )
        response.raise_for_status()
        data = response.json()
        embeddings: list[list[float]] | None = data.get("embeddings")
        if embeddings is None:
            raise RuntimeError("Ollama /api/embed response missing 'embeddings' key")
        return embeddings
