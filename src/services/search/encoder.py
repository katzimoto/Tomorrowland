from __future__ import annotations

import hashlib
from typing import Protocol

DIMENSIONS = 384


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
