"""Unit tests for Document Chat scope model and Qdrant filter builder."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from qdrant_client.models import Filter, MatchAny, MatchValue

from services.chat.models import ChatScope
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
