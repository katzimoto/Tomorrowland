from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol

import httpx

from services.chunking.splitter import chunk_text as _chunk_text

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


class OpenAICompatibleEmbeddingEncoder:
    """Encoder using an OpenAI-compatible ``/v1/embeddings`` endpoint.

    Supports providers such as Ollama (``/v1/embeddings``), LiteLLM, or any
    OpenAI-proxy that exposes the standard OpenAI embedding API shape::

        {
          "data": [
            {"index": 0, "embedding": [...]},
            {"index": 1, "embedding": [...]},
          ]
        }

    Batch results are sorted by ``index`` so the return order always matches
    the input order regardless of server-side response ordering.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        dimension: int = 768,
        api_key: str = "",
        timeout: float = 180.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._api_key = api_key
        self._timeout = timeout

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        return self._embed_batch([text])[0]

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed_batch(texts)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._base_url}/v1/embeddings"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }

        logger.debug(
            "OpenAI-compatible embed model=%s batch_size=%d",
            self._model,
            len(texts),
        )

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to embedding service at {self._base_url}."
            ) from None
        except httpx.TimeoutException:
            raise RuntimeError(
                f"Embedding request timed out after {self._timeout}s."
            ) from None

        response.raise_for_status()
        data = response.json()

        raw_data: list[dict[str, Any]] | None = data.get("data")
        if raw_data is None:
            raise RuntimeError(
                "OpenAI-compatible /v1/embeddings response missing 'data' key"
            )

        # Sort by index to guarantee input-order stability
        sorted_data = sorted(raw_data, key=lambda entry: entry.get("index", 0))
        embeddings: list[list[float]] = []
        for entry in sorted_data:
            emb: list[float] | None = entry.get("embedding")
            if emb is None:
                raise RuntimeError(
                    "OpenAI-compatible /v1/embeddings response entry missing 'embedding'"
                )
            embeddings.append(emb)

        return embeddings


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
        timeout: float = 180.0,
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
        """Embed *texts*, splitting any that exceed the context window and
        mean-pooling the sub-chunk vectors back to one vector per input text.

        Dense scripts (Hebrew, Arabic, CJK) tokenise at 1–2 chars/token, so
        the old ``len/4`` estimate was too optimistic.  Using 3 chars/token as
        the split boundary is conservative enough to prevent context overflows
        while keeping sub-chunks large.  Sub-chunk vectors are averaged
        (mean-pooled) so no content is lost from the returned embedding.
        """
        if self._max_tokens is not None:
            char_limit = self._max_tokens * 3  # conservative 3 chars/token
            # Expand each input text into one or more sub-chunks and record
            # the slice of the flat list that belongs to each original text.
            expanded: list[str] = []
            spans: list[tuple[int, int]] = []  # (start, end) into expanded
            for i, text in enumerate(texts):
                start = len(expanded)
                if len(text) > char_limit:
                    # Delegate to the pipeline chunker so we get the same
                    # sentence-boundary-aware splitting used upstream.
                    sub_chunks = _chunk_text(text, max_tokens=self._max_tokens) or [
                        text[:char_limit]
                    ]
                    logger.warning(
                        "Embedding text at index %d split into %d sub-chunks "
                        "(len=%d char_limit=%d model=%s)",
                        i,
                        len(sub_chunks),
                        len(text),
                        char_limit,
                        self._model,
                    )
                    expanded.extend(sub_chunks)
                else:
                    expanded.append(text)
                spans.append((start, len(expanded)))

            raw = self._request_embed(expanded)

            # Mean-pool sub-chunk vectors back to one vector per original text.
            result: list[list[float]] = []
            for start, end in spans:
                vecs = raw[start:end]
                if len(vecs) == 1:
                    result.append(vecs[0])
                else:
                    dim = len(vecs[0])
                    mean_vec = [sum(v[d] for v in vecs) / len(vecs) for d in range(dim)]
                    result.append(mean_vec)
            return result

        return self._request_embed(texts)

    def _request_embed(self, texts: list[str]) -> list[list[float]]:
        """POST *texts* to ``/api/embed`` and return the raw embedding list."""
        url = f"{self._base_url}/api/embed"
        payload: dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }
        # Pin num_ctx at request level so it overrides the Modelfile default.
        # nomic-embed-text ships with PARAMETER num_ctx 8192 in its Modelfile,
        # but n_ctx_train=2048 — loading with 8192 wastes memory and logs a
        # warning.  Request-level options take the highest precedence in Ollama.
        if self._max_tokens is not None:
            payload["options"] = {"num_ctx": self._max_tokens}
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
