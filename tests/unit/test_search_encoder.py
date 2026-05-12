from __future__ import annotations

import pytest

from services.search.encoder import DeterministicTestEncoder


def test_encoder_returns_384_dimensions() -> None:
    encoder = DeterministicTestEncoder()
    vec = encoder.encode("hello world")

    assert len(vec) == 384


def test_encoder_is_deterministic() -> None:
    encoder = DeterministicTestEncoder()
    vec1 = encoder.encode("hello world")
    vec2 = encoder.encode("hello world")

    assert vec1 == vec2


def test_encoder_different_inputs_different_vectors() -> None:
    encoder = DeterministicTestEncoder()
    vec1 = encoder.encode("hello world")
    vec2 = encoder.encode("goodbye world")

    assert vec1 != vec2


def test_encoder_values_are_floats() -> None:
    encoder = DeterministicTestEncoder()
    vec = encoder.encode("test")

    assert all(isinstance(v, float) for v in vec)


def test_encoder_values_in_reasonable_range() -> None:
    encoder = DeterministicTestEncoder()
    vec = encoder.encode("test")

    # Values should be between -1 and 1 (deterministic hash based)
    assert all(-1.0 <= v <= 1.0 for v in vec)


def test_encoder_empty_string() -> None:
    encoder = DeterministicTestEncoder()
    vec = encoder.encode("")

    assert len(vec) == 384


def test_encoder_batch_encoding() -> None:
    encoder = DeterministicTestEncoder()
    texts = ["first", "second", "third"]
    vectors = encoder.encode_batch(texts)

    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)
    assert vectors[0] != vectors[1]


def test_encoder_batch_empty_list() -> None:
    encoder = DeterministicTestEncoder()
    vectors = encoder.encode_batch([])

    assert vectors == []


def test_encoder_non_string_raises() -> None:
    encoder = DeterministicTestEncoder()

    with pytest.raises(TypeError, match="text must be a string"):
        encoder.encode(123)  # type: ignore[arg-type]


def test_encoder_no_external_dependencies() -> None:
    """Ensure the encoder module does not import torch, transformers, etc."""
    import sys

    forbidden = {"torch", "transformers", "sentence_transformers", "onnxruntime"}
    imported = set(sys.modules.keys())
    intersection = forbidden & imported
    assert not intersection, f"Forbidden modules imported: {intersection}"
