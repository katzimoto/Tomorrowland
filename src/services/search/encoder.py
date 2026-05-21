from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol

import httpx

DIMENSIONS = 384

logger = logging.getLogger(__name__)


class TextEncoder(Protocol):
    """Protocol for text-to-vector encoders."""

    @property
    def dimension(self) -> int:
        """Return the vector dimension produced by this encoder."""
        ...

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

    @property
    def dimension(self) -> int:
        return DIMENSIONS

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


def _parse_ollama_error(response: httpx.Response) -> str | None:
    """Extract the error message from an Ollama error response body."""
    try:
        body = response.json()
        msg: object = body.get("error")
        return str(msg) if msg else None
    except Exception:
        return None


def _estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text* using a character-based heuristic."""
    return max(1, int(len(text) / 4.0))


class OllamaEmbeddingEncoder:
    """Production encoder using Ollama's modern embedding endpoint.

    Calls the Ollama ``/api/embed`` endpoint for both single-text and batch
    embedding.  The legacy ``/api/embeddings`` endpoint is not used.

    When *max_tokens* is set, every text is validated before being sent to
    Ollama.  Texts that exceed the limit raise ``ValueError`` before any API
    call — this serves as a defensive guard even when upstream chunking is
    correct.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "nomic-embed-text",
        dimension: int = 768,
        timeout: float = 60.0,
        max_tokens: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._timeout = timeout
        self._max_tokens = max_tokens

    @property
    def dimension(self) -> int:
        return self._dimension

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
        if self._max_tokens is not None:
            for i, text in enumerate(texts):
                token_count = _estimate_tokens(text)
                if token_count > self._max_tokens:
                    raise ValueError(
                        f"Embedding text at index {i} exceeds max_tokens={self._max_tokens} "
                        f"(estimated {token_count} tokens)"
                    )
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
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout)
        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self._base_url}. "
                f"Ensure Ollama is running and reachable."
            ) from None
        except httpx.TimeoutException:
            raise RuntimeError(
                f"Ollama request timed out after {self._timeout}s. "
                f"Model '{self._model}' may still be loading."
            ) from None
        if response.status_code == 400:
            error_body = _parse_ollama_error(response)
            if error_body and "input length exceeds" in error_body.lower():
                raise ValueError(
                    f"Ollama embedding text exceeds model context length. "
                    f"Model='{self._model}' max_tokens={self._max_tokens} "
                    f"error='{error_body}'"
                )
            response.raise_for_status()
        elif response.status_code == 404:
            error_body = _parse_ollama_error(response)
            if error_body and "not found" in error_body and "pull" in error_body:
                raise RuntimeError(
                    f"Ollama model '{self._model}' not found. "
                    f"Try pulling it first: ollama pull {self._model}"
                )
            raise RuntimeError(
                f"Ollama model '{self._model}' does not support the /api/embed endpoint. "
                f"Update Ollama or use a different model."
            )
        response.raise_for_status()
        data = response.json()
        embeddings: list[list[float]] | None = data.get("embeddings")
        if embeddings is None:
            raise RuntimeError("Ollama /api/embed response missing 'embeddings' key")
        return embeddings
