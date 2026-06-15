"""Tests for the search reranker (post-retrieval relevance scoring).

Covers:
- NoOpSearchReranker (pass-through)
- EndpointSearchReranker (TEI-compatible /rerank HTTP endpoint)
- LLMSearchReranker (Ollama prompt-based fallback)
- build_reranker factory
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.search.factory import build_reranker
from services.search.models import SearchResult
from services.search.reranker import (
    EndpointSearchReranker,
    LLMSearchReranker,
    NoOpSearchReranker,
    SearchReranker,
)


def _make_result(
    document_id: str = "doc-1",
    score: float = 0.5,
    title: str | None = None,
    chunk_text: str | None = None,
) -> SearchResult:
    return SearchResult(
        document_id=document_id,
        score=score,
        title=title,
        chunk_text=chunk_text,
    )


def _make_llm_mock(*, responses: list[str] | None = None) -> MagicMock:
    m = MagicMock()
    if responses:
        m.generate.side_effect = responses
    else:
        m.generate.return_value = "5"
    return m


# ---------------------------------------------------------------------------
# SearchReranker protocol
# ---------------------------------------------------------------------------


def test_search_reranker_protocol_has_rerank() -> None:
    """The SearchReranker protocol should define 'rerank'."""
    assert hasattr(SearchReranker, "rerank")
    assert inspect.isfunction(SearchReranker.rerank)


# ---------------------------------------------------------------------------
# NoOpSearchReranker
# ---------------------------------------------------------------------------


def test_noop_reranker_returns_results_unchanged() -> None:
    """NoOpSearchReranker must return the exact same list."""
    reranker = NoOpSearchReranker()
    results = [
        _make_result("doc-1", 0.9, title="Hello", chunk_text="hello"),
        _make_result("doc-2", 0.5, title="World", chunk_text="world"),
    ]
    result = reranker.rerank("test query", results)
    assert result is results
    assert result == results


def test_noop_reranker_empty_list() -> None:
    """NoOpSearchReranker must handle empty input."""
    reranker = NoOpSearchReranker()
    assert reranker.rerank("query", []) == []


def test_noop_reranker_preserves_result_structure() -> None:
    """NoOpSearchReranker must preserve all fields in each SearchResult."""
    reranker = NoOpSearchReranker()
    results = [
        SearchResult(
            document_id="doc-1",
            score=0.8,
            title="Doc 1",
            chunk_text="text",
            metadata={"chunk_id": "chunk-1"},
        )
    ]
    result = reranker.rerank("question", results)
    assert result[0].document_id == "doc-1"
    assert result[0].score == pytest.approx(0.8)
    assert result[0].title == "Doc 1"
    assert result[0].chunk_text == "text"
    assert result[0].metadata == {"chunk_id": "chunk-1"}


# ---------------------------------------------------------------------------
# EndpointSearchReranker
# ---------------------------------------------------------------------------


def _make_endpoint_response(scores: list[float]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"scores": scores}
    resp.raise_for_status = MagicMock()
    return resp


def test_endpoint_reranker_orders_by_score() -> None:
    """Returned results must be ordered by reranker score descending."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
        top_n=10,
    )
    results = [
        _make_result("d1", chunk_text="low", score=0.3),
        _make_result("d2", chunk_text="high", score=0.9),
        _make_result("d3", chunk_text="medium", score=0.5),
    ]
    resp = _make_endpoint_response([0.2, 0.9, 0.5])

    with patch("services.search.reranker.httpx.post", return_value=resp):
        result = reranker.rerank("question", results)

    assert [r.document_id for r in result] == ["d2", "d3", "d1"]
    # Scores are replaced with reranker scores
    assert result[0].score == pytest.approx(0.9)
    assert result[1].score == pytest.approx(0.5)
    assert result[2].score == pytest.approx(0.2)


def test_endpoint_reranker_filters_below_min_score() -> None:
    """Results below min_score must be dropped."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.5,
        top_n=10,
    )
    results = [
        _make_result("d1", chunk_text="a", score=0.5),
        _make_result("d2", chunk_text="b", score=0.5),
        _make_result("d3", chunk_text="c", score=0.5),
    ]
    resp = _make_endpoint_response([0.1, 0.9, 0.3])

    with patch("services.search.reranker.httpx.post", return_value=resp):
        result = reranker.rerank("question", results)

    assert [r.document_id for r in result] == ["d2"]


def test_endpoint_reranker_respects_top_n() -> None:
    """At most top_n results must be returned."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
        top_n=2,
    )
    results = [_make_result(f"d{i}", chunk_text=f"text {i}") for i in range(5)]
    resp = _make_endpoint_response([0.9, 0.8, 0.7, 0.6, 0.5])

    with patch("services.search.reranker.httpx.post", return_value=resp):
        result = reranker.rerank("question", results)

    assert len(result) == 2


def test_endpoint_reranker_empty_input() -> None:
    """Empty result list must return empty list without calling endpoint."""
    reranker = EndpointSearchReranker(url="http://reranker:8080/rerank")
    assert reranker.rerank("question", []) == []


def test_endpoint_reranker_falls_back_on_error() -> None:
    """On any HTTP error, the reranker must return results unchanged."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
        top_n=10,
    )
    results = [_make_result("d1", chunk_text="important", score=0.9)]

    with patch(
        "services.search.reranker.httpx.post",
        side_effect=httpx.ConnectError("down"),
    ):
        result = reranker.rerank("question", results)

    assert result is results
    assert result == results


def test_endpoint_reranker_wrong_score_count_returns_original() -> None:
    """When the endpoint returns the wrong number of scores, return results unchanged."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
        top_n=10,
    )
    results = [
        _make_result("d1", chunk_text="a", score=0.5),
        _make_result("d2", chunk_text="b", score=0.5),
    ]
    resp = _make_endpoint_response([0.9])  # only 1 score for 2 chunks

    with patch("services.search.reranker.httpx.post", return_value=resp):
        result = reranker.rerank("question", results)

    assert result is results
    assert len(result) == 2


def test_endpoint_reranker_sends_query_and_texts() -> None:
    """The endpoint must receive the query and chunk texts in the request body."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
    )
    results = [
        _make_result("d1", chunk_text="chunk one", score=0.5),
        _make_result("d2", chunk_text="chunk two", score=0.5),
    ]
    resp = _make_endpoint_response([0.9, 0.8])

    with patch("services.search.reranker.httpx.post", return_value=resp) as m:
        reranker.rerank("What is the answer?", results)

    payload = m.call_args[1]["json"]
    assert payload["query"] == "What is the answer?"
    assert payload["texts"] == ["chunk one", "chunk two"]


def test_endpoint_reranker_sends_model_when_configured() -> None:
    """When model is set, it must be included in the request payload."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        model="BAAI/bge-reranker-v2-m3",
        min_score=0.0,
    )
    results = [_make_result("d1", chunk_text="text", score=0.5)]
    resp = _make_endpoint_response([0.8])

    with patch("services.search.reranker.httpx.post", return_value=resp) as m:
        reranker.rerank("question", results)

    payload = m.call_args[1]["json"]
    assert payload["model"] == "BAAI/bge-reranker-v2-m3"


def test_endpoint_reranker_preserves_fields_in_result() -> None:
    """Reranked results must preserve title, chunk_text, and metadata."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
        top_n=10,
    )
    results = [
        SearchResult(
            document_id="doc-1",
            score=0.5,
            title="Document Title",
            chunk_text="The full text",
            metadata={"source": "upload"},
        ),
    ]
    resp = _make_endpoint_response([0.95])

    with patch("services.search.reranker.httpx.post", return_value=resp):
        result = reranker.rerank("question", results)

    assert len(result) == 1
    assert result[0].document_id == "doc-1"
    assert result[0].score == pytest.approx(0.95)
    assert result[0].title == "Document Title"
    assert result[0].chunk_text == "The full text"
    assert result[0].metadata == {"source": "upload"}


def test_endpoint_reranker_none_chunk_text_sends_empty() -> None:
    """When chunk_text is None, send empty string."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
    )
    results = [_make_result("d1", chunk_text=None, score=0.5)]
    resp = _make_endpoint_response([0.8])

    with patch("services.search.reranker.httpx.post", return_value=resp) as m:
        reranker.rerank("question", results)

    payload = m.call_args[1]["json"]
    assert payload["texts"] == [""]


def test_endpoint_reranker_http_error_returns_original() -> None:
    """On HTTP status error, return results unchanged."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
        top_n=10,
    )
    results = [_make_result("d1", score=0.9)]
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=MagicMock()
    )

    with patch("services.search.reranker.httpx.post", return_value=resp):
        result = reranker.rerank("question", results)

    assert result is results


def test_endpoint_reranker_tie_breaks_by_document_id() -> None:
    """When scores are equal, sort by document_id ascending as tie-breaker."""
    reranker = EndpointSearchReranker(
        url="http://reranker:8080/rerank",
        min_score=0.0,
        top_n=10,
    )
    results = [
        _make_result("c", score=0.5),
        _make_result("a", score=0.5),
        _make_result("b", score=0.5),
    ]
    resp = _make_endpoint_response([0.5, 0.5, 0.5])

    with patch("services.search.reranker.httpx.post", return_value=resp):
        result = reranker.rerank("question", results)

    assert [r.document_id for r in result] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# LLMSearchReranker
# ---------------------------------------------------------------------------


def test_llm_reranker_orders_by_score_desc() -> None:
    """Results must be ordered by LLM relevance score descending."""
    llm = _make_llm_mock(responses=["3", "9", "6"])
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10)
    results = [
        _make_result("d1", chunk_text="a", score=0.5),
        _make_result("d2", chunk_text="b", score=0.5),
        _make_result("d3", chunk_text="c", score=0.5),
    ]
    result = reranker.rerank("question", results)
    # Scores: 0.3, 0.9, 0.6 → ordered: d2 (0.9), d3 (0.6), d1 (0.3)
    assert [r.document_id for r in result] == ["d2", "d3", "d1"]


def test_llm_reranker_filters_below_min_score() -> None:
    """Results scoring below min_score must be dropped."""
    # min_score=0.3 (maps to LLM score >= 3.0 on 0-10 scale)
    llm = _make_llm_mock(responses=["2", "5", "9"])
    reranker = LLMSearchReranker(llm, min_score=0.3, top_n=10)
    results = [
        _make_result("d1", chunk_text="low", score=0.5),
        _make_result("d2", chunk_text="medium", score=0.5),
        _make_result("d3", chunk_text="high", score=0.5),
    ]
    result = reranker.rerank("question", results)
    # LLM scores: 2 (0.2), 5 (0.5), 9 (0.9) — d1 below threshold
    assert len(result) == 2
    assert result[0].document_id == "d3"
    assert result[1].document_id == "d2"


def test_llm_reranker_respects_top_n() -> None:
    """At most top_n results must be returned."""
    llm = _make_llm_mock(responses=["8", "7", "6", "9", "5"])
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=3)
    results = [_make_result(f"d{i}", chunk_text=f"text {i}") for i in range(5)]
    result = reranker.rerank("question", results)
    assert len(result) == 3


def test_llm_reranker_empty_input() -> None:
    """Empty result list must return empty list without calling LLM."""
    llm = _make_llm_mock()
    reranker = LLMSearchReranker(llm)
    assert reranker.rerank("question", []) == []


def test_llm_reranker_parse_score_from_full_response() -> None:
    """The score parser must extract a number from full-sentence responses.

    LLM responses are on a 0-10 scale and get normalized to 0-1.
    """
    llm = _make_llm_mock(
        responses=[
            "The relevance score is 7.",
            "Score: 4",
            "3 out of 10",
        ]
    )
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10)
    results = [
        _make_result("d1", chunk_text="a", score=0.5),
        _make_result("d2", chunk_text="b", score=0.5),
        _make_result("d3", chunk_text="c", score=0.5),
    ]
    result = reranker.rerank("question", results)
    assert len(result) == 3
    # Scores: 0.7, 0.4, 0.3 → ordered: d1 (0.7), d2 (0.4), d3 (0.3)
    assert result[0].document_id == "d1"
    assert result[0].score == pytest.approx(0.7)


def test_llm_reranker_handles_llm_error() -> None:
    """When LLM generate raises, the result gets score 0 (dropped if above min)."""
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("Ollama down")
    reranker = LLMSearchReranker(llm, min_score=0.3, top_n=10)
    results = [
        _make_result("d1", chunk_text="important", score=0.9),
        _make_result("d2", chunk_text="also important", score=0.8),
    ]
    result = reranker.rerank("question", results)
    # Both get score 0.0, which is below min_score=0.3 → dropped
    assert result == []


def test_llm_reranker_calls_generate_with_relevance_prompt() -> None:
    """LLM generate must be called with a prompt containing query and chunk_text."""
    llm = MagicMock()
    llm.generate.return_value = "8"
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10)
    results = [_make_result("d1", chunk_text="specific document text", score=0.7)]
    reranker.rerank("What is the answer?", results)
    prompt = llm.generate.call_args[0][0]
    assert "What is the answer?" in prompt
    assert "specific document text" in prompt


def test_llm_reranker_passes_model_parameter() -> None:
    """When model is set, it must be passed to llm.generate as keyword arg."""
    llm = MagicMock()
    llm.generate.return_value = "8"
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10, model="reranker-model")
    results = [_make_result("d1", chunk_text="text", score=0.5)]
    reranker.rerank("question", results)
    assert llm.generate.call_args[1].get("model") == "reranker-model"


def test_llm_reranker_none_chunk_text_uses_empty() -> None:
    """When chunk_text is None, an empty string must be sent to the LLM."""
    llm = MagicMock()
    llm.generate.return_value = "5"
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10)
    results = [_make_result("d1", chunk_text=None, score=0.5)]
    reranker.rerank("question", results)
    prompt = llm.generate.call_args[0][0]
    assert "Excerpt: " in prompt  # empty excerpt still rendered


def test_llm_reranker_score_clamped_to_range() -> None:
    """LLM scores are clamped to [0, 1] after normalizing from 0-10 scale.

    The _parse_score regex extracts digits (not signs), so "-2" extracts "2"
    → 0.2, and "15" → 1.5 → clamped to 1.0. These are edge cases; the LLM
    should normally produce 0-10 integers.
    """
    llm = _make_llm_mock(responses=["15", "-2"])
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10)
    results = [
        _make_result("d1", chunk_text="a", score=0.5),
        _make_result("d2", chunk_text="b", score=0.5),
    ]
    result = reranker.rerank("question", results)
    # "15" → 1.5 → clamped to 1.0
    assert result[0].document_id == "d1"
    assert result[0].score == pytest.approx(1.0)
    # "-2" → regex matches "2" → 0.2 (already in [0,1])
    assert result[1].score == pytest.approx(0.2)


def test_llm_reranker_unparseable_response_defaults_to_zero() -> None:
    """When the LLM response contains no number, score defaults to 0.0."""
    llm = _make_llm_mock(responses=["irrelevant response", "no number here"])
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10)
    results = [
        _make_result("d1", chunk_text="a", score=0.5),
        _make_result("d2", chunk_text="b", score=0.5),
    ]
    result = reranker.rerank("question", results)
    assert all(r.score == 0.0 for r in result)


def test_llm_reranker_preserves_fields() -> None:
    """Reranked results must preserve title, chunk_text, and metadata."""
    llm = MagicMock()
    llm.generate.return_value = "7"
    reranker = LLMSearchReranker(llm, min_score=0.0, top_n=10)
    results = [
        SearchResult(
            document_id="doc-1",
            score=0.5,
            title="Document Title",
            chunk_text="Full text",
            metadata={"source": "upload"},
        ),
    ]
    result = reranker.rerank("question", results)
    assert len(result) == 1
    assert result[0].document_id == "doc-1"
    assert result[0].score == pytest.approx(0.7)
    assert result[0].title == "Document Title"
    assert result[0].chunk_text == "Full text"
    assert result[0].metadata == {"source": "upload"}


# ---------------------------------------------------------------------------
# build_reranker factory
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Minimal settings stub for build_reranker tests."""

    def __init__(
        self,
        *,
        search_reranker_enabled: bool = False,
        search_reranker_url: str = "",
        search_reranker_model: str = "BAAI/bge-reranker-v2-m3",
        search_reranker_min_score: float = 0.0,
        search_reranker_depth: int = 20,
        search_reranker_timeout: float = 10.0,
        ollama_reranker_model: str = "",
        ollama_utility_model: str = "qwen3:1.7b",
        ollama_model: str = "qwen3:4b",
    ) -> None:
        self.search_reranker_enabled = search_reranker_enabled
        self.search_reranker_url = search_reranker_url
        self.search_reranker_model = search_reranker_model
        self.search_reranker_min_score = search_reranker_min_score
        self.search_reranker_depth = search_reranker_depth
        self.search_reranker_timeout = search_reranker_timeout
        self.ollama_reranker_model = ollama_reranker_model
        self.ollama_utility_model = ollama_utility_model
        self.ollama_model = ollama_model

    @property
    def effective_utility_model(self) -> str:
        return self.ollama_utility_model or self.ollama_model

    @property
    def effective_reranker_model(self) -> str:
        return self.ollama_reranker_model or self.effective_utility_model


def test_build_reranker_disabled_returns_noop() -> None:
    """When search_reranker_enabled is False, return NoOpSearchReranker."""
    settings: Any = _FakeSettings(search_reranker_enabled=False)
    reranker = build_reranker(settings, llm_provider=None)
    assert isinstance(reranker, NoOpSearchReranker)


def test_build_reranker_endpoint_when_url_set() -> None:
    """When search_reranker_url is set, return EndpointSearchReranker."""
    settings: Any = _FakeSettings(
        search_reranker_enabled=True,
        search_reranker_url="http://reranker:8080/rerank",
    )
    reranker = build_reranker(settings, llm_provider=None)
    assert isinstance(reranker, EndpointSearchReranker)
    assert reranker._url == "http://reranker:8080/rerank"


def test_build_reranker_llm_fallback_when_no_url() -> None:
    """When enabled but no URL, fall back to LLMSearchReranker."""
    settings: Any = _FakeSettings(search_reranker_enabled=True, search_reranker_url="")
    llm = MagicMock()
    reranker = build_reranker(settings, llm_provider=llm)
    assert isinstance(reranker, LLMSearchReranker)


def test_build_reranker_noop_when_enabled_no_url_no_llm() -> None:
    """When enabled, no URL, and no llm_provider, return NoOpSearchReranker."""
    settings: Any = _FakeSettings(search_reranker_enabled=True, search_reranker_url="")
    reranker = build_reranker(settings, llm_provider=None)
    assert isinstance(reranker, NoOpSearchReranker)


def test_build_reranker_passes_endpoint_settings() -> None:
    """EndpointSearchReranker must receive all configured settings."""
    settings: Any = _FakeSettings(
        search_reranker_enabled=True,
        search_reranker_url="http://reranker:8080/rerank",
        search_reranker_model="custom-model",
        search_reranker_min_score=0.2,
        search_reranker_depth=10,
        search_reranker_timeout=5.0,
    )
    reranker = build_reranker(settings, llm_provider=None)
    assert isinstance(reranker, EndpointSearchReranker)
    assert reranker._model == "custom-model"
    assert reranker._min_score == 0.2
    assert reranker._top_n == 10
    assert reranker._timeout == 5.0


def test_build_reranker_passes_llm_settings() -> None:
    """LLMSearchReranker must receive configured settings and effective model."""
    settings: Any = _FakeSettings(
        search_reranker_enabled=True,
        search_reranker_url="",
        search_reranker_min_score=0.3,
        search_reranker_depth=15,
        ollama_reranker_model="reranker-model",
        ollama_model="qwen3:4b",
    )
    llm = MagicMock()
    reranker = build_reranker(settings, llm_provider=llm)
    assert isinstance(reranker, LLMSearchReranker)
    assert reranker._min_score == 0.3
    assert reranker._top_n == 15
    # effective_reranker_model chains: ollama_reranker_model → utility → main
    assert settings.effective_reranker_model == "reranker-model"
    assert reranker._model == "reranker-model"


def test_build_reranker_effective_model_falls_back_to_utility() -> None:
    """When ollama_reranker_model is empty, effective model falls back to utility."""
    settings: Any = _FakeSettings(
        search_reranker_enabled=True,
        search_reranker_url="",
        ollama_reranker_model="",  # empty, falls back to utility
        ollama_utility_model="qwen3:1.7b",
        ollama_model="qwen3:4b",
    )
    llm = MagicMock()
    reranker = build_reranker(settings, llm_provider=llm)
    assert reranker._model == "qwen3:1.7b"


def test_build_reranker_effective_model_falls_back_to_main() -> None:
    """When both reranker and utility are empty, fall back to main model."""
    settings: Any = _FakeSettings(
        search_reranker_enabled=True,
        search_reranker_url="",
        ollama_reranker_model="",
        ollama_utility_model="",
        ollama_model="qwen3:4b",
    )
    llm = MagicMock()
    reranker = build_reranker(settings, llm_provider=llm)
    assert reranker._model == "qwen3:4b"


def test_build_reranker_url_strips_trailing_slash() -> None:
    """Trailing slash in URL must be stripped."""
    settings: Any = _FakeSettings(
        search_reranker_enabled=True,
        search_reranker_url="http://reranker:8080/rerank/",
    )
    reranker = build_reranker(settings, llm_provider=None)
    assert reranker._url == "http://reranker:8080/rerank"
