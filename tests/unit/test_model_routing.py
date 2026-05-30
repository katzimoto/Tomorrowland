"""Tests for role-based Ollama model routing (issue #513).

Proves:
- Answer tasks (RAG) route to OLLAMA_MODEL (main).
- Query rewrite, auto-tag, key-points LLM augmentation, chunk-level summary
  map route to OLLAMA_UTILITY_MODEL.
- Reranking routes to OLLAMA_RERANKER_MODEL, with fallback chain to utility
  then main.
- Empty OLLAMA_UTILITY_MODEL falls back to OLLAMA_MODEL.
- Single-model behavior (all three empty / same value) remains compatible.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from services.chat.message_service import rewrite_query
from services.intelligence.ollama_client import OllamaClient
from services.intelligence.worker import IntelligenceWorker
from services.rag.reranker import CrossEncoderReranker
from shared.config import Settings

# ---------------------------------------------------------------------------
# Settings: effective model resolution
# ---------------------------------------------------------------------------


class TestEffectiveModelResolution:
    def test_utility_falls_back_to_main(self) -> None:
        s = Settings(ollama_model="main-model", ollama_utility_model="")
        assert s.effective_utility_model == "main-model"

    def test_utility_uses_own_value_when_set(self) -> None:
        s = Settings(ollama_model="main-model", ollama_utility_model="utility-model")
        assert s.effective_utility_model == "utility-model"

    def test_reranker_falls_back_through_utility_to_main(self) -> None:
        s = Settings(
            ollama_model="main-model",
            ollama_utility_model="",
            ollama_reranker_model="",
        )
        assert s.effective_reranker_model == "main-model"

    def test_reranker_falls_back_to_utility(self) -> None:
        s = Settings(
            ollama_model="main-model",
            ollama_utility_model="utility-model",
            ollama_reranker_model="",
        )
        assert s.effective_reranker_model == "utility-model"

    def test_reranker_uses_own_value_when_set(self) -> None:
        s = Settings(
            ollama_model="main-model",
            ollama_utility_model="utility-model",
            ollama_reranker_model="reranker-model",
        )
        assert s.effective_reranker_model == "reranker-model"

    def test_single_model_compat(self) -> None:
        """All three empty → effective_utility and effective_reranker both == main model."""
        s = Settings(
            ollama_model="mistral",
            ollama_utility_model="",
            ollama_reranker_model="",
        )
        assert s.effective_utility_model == "mistral"
        assert s.effective_reranker_model == "mistral"


# ---------------------------------------------------------------------------
# IntelligenceWorker: task routing
# ---------------------------------------------------------------------------


def _make_worker(
    main_model: str = "main-model",
    utility_model: str | None = None,
    generate_return: str = "[]",
) -> tuple[IntelligenceWorker, MagicMock]:
    """Return (worker, mock_ollama_client) pair."""
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama._model = main_model
    mock_ollama.generate.return_value = generate_return
    mock_ollama.parse_json_array.return_value = []

    mock_repo = MagicMock()
    mock_config: dict[str, Any] = {
        "feature.summarization": True,
        "feature.entity_extraction": True,
        "feature.auto_tagging": True,
        "feature.key_points": False,  # rule-based only by default
    }

    worker = IntelligenceWorker(
        repository=mock_repo,
        ollama_client=mock_ollama,
        config_source=mock_config,
        utility_model=utility_model,
    )
    return worker, mock_ollama


class TestIntelligenceWorkerRouting:
    def test_entity_extraction_uses_main_model(self) -> None:
        worker, mock_ollama = _make_worker(utility_model="utility-model")
        worker._extract_entities(uuid4(), "Some content about Alice at Acme Corp.")
        # generate called with no model override (None → client default = main)
        calls = mock_ollama.generate.call_args_list
        assert len(calls) == 1
        _, kwargs = calls[0]
        assert kwargs.get("model") is None

    def test_auto_tag_uses_utility_model(self) -> None:
        worker, mock_ollama = _make_worker(utility_model="utility-model")
        worker._auto_tag(uuid4(), "Python web framework REST API")
        calls = mock_ollama.generate.call_args_list
        assert len(calls) == 1
        _, kwargs = calls[0]
        assert kwargs.get("model") == "utility-model"

    def test_auto_tag_falls_back_to_none_when_no_utility(self) -> None:
        """When utility_model is None, auto-tag passes None → client uses main model."""
        worker, mock_ollama = _make_worker(utility_model=None)
        worker._auto_tag(uuid4(), "Python web framework REST API")
        _, kwargs = mock_ollama.generate.call_args
        assert kwargs.get("model") is None

    def test_key_points_llm_uses_utility_model(self) -> None:
        worker, mock_ollama = _make_worker(utility_model="utility-model")
        # Enable LLM augmentation via config
        worker._config["feature.key_points"] = True  # type: ignore[index]
        worker._config["llm.key_points_prompt"] = "List key points:"  # type: ignore[index]
        mock_ollama.parse_json_array.return_value = ["point one", "point two"]
        worker._extract_key_points(uuid4(), "Content about key topics.")
        calls = mock_ollama.generate.call_args_list
        assert len(calls) == 1
        _, kwargs = calls[0]
        assert kwargs.get("model") == "utility-model"

    def test_summary_map_uses_utility_reduce_uses_main(self) -> None:
        """Long doc: map chunks use utility model, reduce uses main (None)."""
        worker, mock_ollama = _make_worker(utility_model="utility-model")
        # Patch to force map-reduce path (content longer than MAX_SUMMARIZE_CHARS)
        long_content = "word " * 10_000  # well above any threshold
        mock_ollama.generate.return_value = (
            '{"summary": "chunk summary", "bullets": [], "status": "ok", '
            '"language": "en", "document_type": "doc", "source_text": ""}'
        )

        with patch(
            "services.intelligence.worker.normalize_summary_output",
            return_value={
                "summary": "final",
                "bullets": [],
                "status": "ok",
                "language": "en",
                "document_type": "doc",
                "source_text": "",
            },
        ):
            worker._summarize(uuid4(), long_content)

        calls = mock_ollama.generate.call_args_list
        # At least 2 calls: ≥1 map (utility) + 1 reduce (main/None)
        assert len(calls) >= 2
        map_models = [c[1].get("model") for c in calls[:-1]]
        reduce_model = calls[-1][1].get("model")
        assert all(m == "utility-model" for m in map_models)
        assert reduce_model is None  # reduce uses client default (main)


# ---------------------------------------------------------------------------
# Query rewrite: utility model
# ---------------------------------------------------------------------------


class TestQueryRewriteRouting:
    def _make_messages(self, n_turns: int) -> list[MagicMock]:
        messages = []
        for i in range(n_turns * 2):
            m = MagicMock()
            m.role = "user" if i % 2 == 0 else "assistant"
            m.content = f"message {i}"
            messages.append(m)
        return messages

    def test_rewrite_passes_utility_model_to_generate(self) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.generate.return_value = "rewritten query"
        prior = self._make_messages(2)

        result = rewrite_query("what else?", prior, mock_client, model="utility-model")

        assert result == "rewritten query"
        _, kwargs = mock_client.generate.call_args
        assert kwargs.get("model") == "utility-model"

    def test_rewrite_passes_none_when_no_model(self) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.generate.return_value = "rewritten"
        prior = self._make_messages(2)

        rewrite_query("what else?", prior, mock_client)  # no model kwarg

        _, kwargs = mock_client.generate.call_args
        assert kwargs.get("model") is None

    def test_rewrite_skipped_on_first_turn(self) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        result = rewrite_query("first question", [], mock_client, model="utility-model")
        assert result == "first question"
        mock_client.generate.assert_not_called()


# ---------------------------------------------------------------------------
# CrossEncoderReranker: reranker model
# ---------------------------------------------------------------------------


class TestRerankerModelRouting:
    def _make_chunks(self, n: int = 3) -> list[dict[str, Any]]:
        return [{"chunk_text": f"chunk {i}", "document_id": str(uuid4())} for i in range(n)]

    def test_reranker_passes_reranker_model_to_generate(self) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.generate.return_value = "8"

        reranker = CrossEncoderReranker(
            ollama_client=mock_client,
            min_score=0.0,
            model="reranker-model",
        )
        reranker.rerank(self._make_chunks(), "test question")

        for c in mock_client.generate.call_args_list:
            _, kwargs = c
            assert kwargs.get("model") == "reranker-model"

    def test_reranker_passes_none_when_no_model(self) -> None:
        """No model override → CrossEncoderReranker uses client default."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.generate.return_value = "7"

        reranker = CrossEncoderReranker(
            ollama_client=mock_client,
            min_score=0.0,
        )
        reranker.rerank(self._make_chunks(1), "question")

        _, kwargs = mock_client.generate.call_args
        assert kwargs.get("model") is None

    def test_reranker_fallback_chain_via_settings(self) -> None:
        """effective_reranker_model falls back: reranker → utility → main."""
        s = Settings(
            ollama_model="main",
            ollama_utility_model="utility",
            ollama_reranker_model="",
        )
        # No dedicated reranker → should use utility
        assert s.effective_reranker_model == "utility"

        s2 = Settings(
            ollama_model="main",
            ollama_utility_model="",
            ollama_reranker_model="",
        )
        # No utility either → should use main
        assert s2.effective_reranker_model == "main"
