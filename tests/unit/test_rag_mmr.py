"""Unit tests for MMR diversification of retrieved chunks."""

from __future__ import annotations

from typing import Any

from services.rag.mmr import _lexical_similarity, _tokens, mmr_reorder


def _chunk(text: str, doc: str = "d") -> dict[str, Any]:
    return {"chunk_text": text, "document_id": doc}


class TestLexicalSimilarity:
    def test_identical_token_sets_score_one(self) -> None:
        a = _tokens("the quick brown fox")
        assert _lexical_similarity(a, a) == 1.0

    def test_disjoint_token_sets_score_zero(self) -> None:
        assert _lexical_similarity(_tokens("alpha beta"), _tokens("gamma delta")) == 0.0

    def test_empty_scores_zero(self) -> None:
        assert _lexical_similarity(set(), _tokens("x")) == 0.0


class TestMmrReorder:
    def test_empty_and_degenerate_inputs(self) -> None:
        assert mmr_reorder([], lambda_=0.5, top_k=5) == []
        assert mmr_reorder([_chunk("a")], lambda_=0.5, top_k=0) == []
        one = [_chunk("only")]
        assert mmr_reorder(one, lambda_=0.5, top_k=5) == one

    def test_truncates_to_top_k(self) -> None:
        chunks = [_chunk(f"text number {i}") for i in range(5)]
        out = mmr_reorder(chunks, lambda_=0.5, top_k=3)
        assert len(out) == 3

    def test_lambda_one_preserves_relevance_order(self) -> None:
        chunks = [_chunk("aaa"), _chunk("bbb"), _chunk("ccc"), _chunk("ddd")]
        out = mmr_reorder(chunks, lambda_=1.0, top_k=4)
        assert out == chunks  # pure relevance = input order

    def test_suppresses_near_duplicate(self) -> None:
        # A and A' share almost all tokens; B is unrelated. With diversity
        # weighting, the second pick must be the diverse B, not the near-dup A'.
        a = _chunk("the quick brown fox jumps over the lazy dog", "a")
        a_dup = _chunk("the quick brown fox jumps over the lazy dog today", "a")
        b = _chunk("completely unrelated words about finance and markets", "b")
        out = mmr_reorder([a, a_dup, b], lambda_=0.5, top_k=2)

        assert out[0] is a  # most relevant first
        assert out[1] is b  # diverse pick beats the near-duplicate

    def test_returns_original_dict_objects(self) -> None:
        chunks = [_chunk("one two three"), _chunk("four five six")]
        out = mmr_reorder(chunks, lambda_=0.5, top_k=2)
        assert all(any(o is c for c in chunks) for o in out)

    def test_deterministic_tie_break_prefers_lower_index(self) -> None:
        # Two unrelated chunks with equal relevance contribution at step 2
        # resolve toward the lower input index.
        chunks = [_chunk("alpha", "0"), _chunk("beta", "1"), _chunk("gamma", "2")]
        out_a = mmr_reorder(chunks, lambda_=0.5, top_k=3)
        out_b = mmr_reorder(chunks, lambda_=0.5, top_k=3)
        assert out_a == out_b
