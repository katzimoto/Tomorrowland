"""Unit tests for Document Chat scope model, Qdrant filter builder, and query rewrite."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from qdrant_client.models import Filter, MatchAny, MatchValue

from services.chat.message_service import rewrite_query
from services.chat.models import ChatMessage, ChatScope
from services.rag.service import build_qdrant_filter

# ---------------------------------------------------------------------------
# ChatScope validation
# ---------------------------------------------------------------------------


def test_all_accessible_requires_empty_scope_ids() -> None:
    with pytest.raises(ValidationError, match="scope_ids must be empty"):
        ChatScope(scope_type="all_accessible_documents", scope_ids=["doc-1"])


def test_single_document_requires_exactly_one_id() -> None:
    with pytest.raises(ValidationError, match="exactly one scope_id"):
        ChatScope(scope_type="single_document", scope_ids=[])

    with pytest.raises(ValidationError, match="exactly one scope_id"):
        ChatScope(scope_type="single_document", scope_ids=["doc-1", "doc-2"])


def test_selected_documents_requires_at_least_one_id() -> None:
    with pytest.raises(ValidationError, match="requires at least one scope_id"):
        ChatScope(scope_type="selected_documents", scope_ids=[])


def test_current_search_results_requires_at_least_one_id() -> None:
    with pytest.raises(ValidationError, match="requires at least one scope_id"):
        ChatScope(scope_type="current_search_results", scope_ids=[])


def test_source_requires_at_least_one_id() -> None:
    with pytest.raises(ValidationError, match="requires at least one scope_id"):
        ChatScope(scope_type="source", scope_ids=[])


def test_folder_requires_at_least_one_id() -> None:
    with pytest.raises(ValidationError, match="requires at least one scope_id"):
        ChatScope(scope_type="folder", scope_ids=[])


def test_invalid_scope_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatScope(scope_type="unknown_scope", scope_ids=[])  # type: ignore[arg-type]


def test_valid_scopes_accepted() -> None:
    assert ChatScope(scope_type="all_accessible_documents").scope_ids == []
    assert ChatScope(scope_type="single_document", scope_ids=["d"]).scope_ids == ["d"]
    assert ChatScope(scope_type="selected_documents", scope_ids=["a", "b"]).scope_ids == ["a", "b"]
    assert ChatScope(scope_type="current_search_results", scope_ids=["x"]).scope_ids == ["x"]
    assert ChatScope(scope_type="source", scope_ids=["s"]).scope_ids == ["s"]
    assert ChatScope(scope_type="folder", scope_ids=["f"]).scope_ids == ["f"]


# ---------------------------------------------------------------------------
# build_qdrant_filter
# ---------------------------------------------------------------------------

GROUP_IDS = ["group-a", "group-b"]
DOC_ID = "doc-uuid-1"
DOC_IDS = ["doc-uuid-1", "doc-uuid-2"]
SOURCE_IDS = ["src-uuid-1"]


def _must_keys(flt: Filter | None) -> list[str]:
    if flt is None:
        return []
    return [c.key for c in (flt.must or [])]  # type: ignore[union-attr]


def test_all_accessible_non_admin_group_filter_only() -> None:
    scope = ChatScope(scope_type="all_accessible_documents")
    flt = build_qdrant_filter(scope, GROUP_IDS, allow_all=False)
    assert flt is not None
    keys = _must_keys(flt)
    assert keys == ["group_id"]
    group_condition = flt.must[0]  # type: ignore[index]
    assert isinstance(group_condition.match, MatchAny)
    assert group_condition.match.any == GROUP_IDS


def test_all_accessible_admin_returns_none_filter() -> None:
    scope = ChatScope(scope_type="all_accessible_documents")
    flt = build_qdrant_filter(scope, [], allow_all=True)
    assert flt is None


def test_single_document_adds_document_id_condition() -> None:
    scope = ChatScope(scope_type="single_document", scope_ids=[DOC_ID])
    flt = build_qdrant_filter(scope, GROUP_IDS, allow_all=False)
    assert flt is not None
    keys = _must_keys(flt)
    assert "group_id" in keys
    assert "document_id" in keys

    doc_condition = next(c for c in flt.must if c.key == "document_id")  # type: ignore[union-attr]
    assert isinstance(doc_condition.match, MatchValue)
    assert doc_condition.match.value == DOC_ID


def test_single_document_admin_skips_group_filter() -> None:
    scope = ChatScope(scope_type="single_document", scope_ids=[DOC_ID])
    flt = build_qdrant_filter(scope, [], allow_all=True)
    assert flt is not None
    keys = _must_keys(flt)
    assert "group_id" not in keys
    assert "document_id" in keys


def test_selected_documents_adds_match_any_document_ids() -> None:
    scope = ChatScope(scope_type="selected_documents", scope_ids=DOC_IDS)
    flt = build_qdrant_filter(scope, GROUP_IDS, allow_all=False)
    assert flt is not None
    keys = _must_keys(flt)
    assert "group_id" in keys
    assert "document_id" in keys

    doc_condition = next(c for c in flt.must if c.key == "document_id")  # type: ignore[union-attr]
    assert isinstance(doc_condition.match, MatchAny)
    assert set(doc_condition.match.any) == set(DOC_IDS)


def test_current_search_results_behaves_like_selected_documents() -> None:
    scope_sel = ChatScope(scope_type="selected_documents", scope_ids=DOC_IDS)
    scope_csr = ChatScope(scope_type="current_search_results", scope_ids=DOC_IDS)
    flt_sel = build_qdrant_filter(scope_sel, GROUP_IDS, allow_all=False)
    flt_csr = build_qdrant_filter(scope_csr, GROUP_IDS, allow_all=False)
    # Both should produce identical filter structure
    assert _must_keys(flt_sel) == _must_keys(flt_csr)


def test_source_adds_source_id_condition() -> None:
    scope = ChatScope(scope_type="source", scope_ids=SOURCE_IDS)
    flt = build_qdrant_filter(scope, GROUP_IDS, allow_all=False)
    assert flt is not None
    keys = _must_keys(flt)
    assert "group_id" in keys
    assert "source_id" in keys

    src_condition = next(c for c in flt.must if c.key == "source_id")  # type: ignore[union-attr]
    assert isinstance(src_condition.match, MatchAny)
    assert src_condition.match.any == SOURCE_IDS


def test_group_filter_applied_when_not_allow_all() -> None:
    scope = ChatScope(scope_type="all_accessible_documents")
    flt = build_qdrant_filter(scope, GROUP_IDS, allow_all=False)
    assert flt is not None
    assert any(c.key == "group_id" for c in (flt.must or []))  # type: ignore[union-attr]


def test_group_filter_skipped_when_allow_all() -> None:
    scope = ChatScope(scope_type="single_document", scope_ids=[DOC_ID])
    flt = build_qdrant_filter(scope, GROUP_IDS, allow_all=True)
    assert flt is not None
    assert not any(c.key == "group_id" for c in (flt.must or []))  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Query rewrite
# ---------------------------------------------------------------------------

_UUID1 = UUID("00000000-0000-0000-0000-000000000001")
_UUID2 = UUID("00000000-0000-0000-0000-000000000002")
_NOW = datetime(2026, 1, 1)


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(
        id=_UUID1,
        session_id=_UUID2,
        role=role,
        content=content,
        created_at=_NOW,
    )


def _mock_ollama(response: str = "") -> MagicMock:
    client = MagicMock()
    client.generate.return_value = response
    return client


def test_rewrite_skipped_for_first_turn() -> None:
    """No rewrite call when session has fewer than one prior turn."""
    client = _mock_ollama("standalone query")
    result = rewrite_query("What about renewal?", [], client)
    assert result == "What about renewal?"
    client.generate.assert_not_called()


def test_rewrite_skipped_for_single_message() -> None:
    """No rewrite call with only a user message (no prior assistant reply)."""
    client = _mock_ollama("standalone query")
    prior = [_msg("user", "What does the contract say?")]
    result = rewrite_query("What about renewal?", prior, client)
    assert result == "What about renewal?"
    client.generate.assert_not_called()


def test_rewrite_resolves_references() -> None:
    """Multi-turn: 'what about renewal?' rewrites to standalone query."""
    client = _mock_ollama("contract renewal terms and conditions")
    prior = [
        _msg("user", "What does the contract say about termination?"),
        _msg("assistant", "The contract allows termination with 30 days notice."),
    ]
    result = rewrite_query("What about renewal?", prior, client)
    assert result == "contract renewal terms and conditions"
    assert client.generate.called


def test_rewrite_uses_last_four_pairs() -> None:
    """Only the last 4 user+assistant pairs are included in the prompt."""
    client = _mock_ollama("standalone query")
    prior = []
    for i in range(6):
        prior.append(_msg("user", f"Q{i}"))
        prior.append(_msg("assistant", f"A{i}"))
    rewrite_query("Final question?", prior, client)
    assert client.generate.called
    prompt = client.generate.call_args[0][0]
    # Should only contain last 4 pairs (Q2-A2 through Q5-A5)
    assert "Q0" not in prompt
    assert "Q1" not in prompt
    assert "Q2" in prompt
    assert "Q5" in prompt


def test_rewrite_fallback_on_ollama_error() -> None:
    """Ollama unavailable falls back to raw message, does not raise."""
    client = _mock_ollama()
    client.generate.side_effect = RuntimeError("Ollama is down")
    prior = [
        _msg("user", "What about deadline?"),
        _msg("assistant", "The deadline is Dec 31."),
    ]
    result = rewrite_query("What about penalties?", prior, client)
    assert result == "What about penalties?"
    assert client.generate.called


def test_rewrite_fallback_on_empty_response() -> None:
    """Empty response from Ollama falls back to raw message."""
    client = _mock_ollama("")
    prior = [
        _msg("user", "Q1"),
        _msg("assistant", "A1"),
    ]
    result = rewrite_query("Q2", prior, client)
    assert result == "Q2"
