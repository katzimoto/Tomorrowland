"""Tests for uniform filter enforcement across BM25 and vector search results.

Covers:
- _map_filters: frontend dict → DocumentSearchFilters (including date_to)
- _qdrant_extra_conditions: language filter pushed into Qdrant payload
- _matches_filters: post-merge predicate for each filter type
- Hybrid scenarios where one backend returns a result the other would filter out
- Empty result when all candidates are filtered
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from qdrant_client.models import FieldCondition, MatchAny

from services.api.routers.search import (
    _map_filters,
    _matches_filters,
    _qdrant_extra_conditions,
)
from services.documents.models import DocumentRow
from services.search.meili_types import DocumentSearchFilters

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc(
    *,
    source: str = "folder",
    mime_type: str = "text/plain",
    source_language: str | None = "en",
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> DocumentRow:
    now = datetime.now(UTC)
    return DocumentRow(
        id=uuid4(),
        source_id=uuid4(),
        external_id="test.txt",
        source=source,  # type: ignore[arg-type]
        mime_type=mime_type,
        source_language=source_language,
        metadata=metadata or {},
        created_at=created_at or now,
        updated_at=now,
    )


def _filters(**kwargs: object) -> DocumentSearchFilters:
    return DocumentSearchFilters(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _map_filters
# ---------------------------------------------------------------------------


class TestMapFilters:
    def test_empty_raw_returns_empty_filters(self) -> None:
        f = _map_filters({})
        assert f.source == []
        assert f.mime_type == []
        assert f.language == []
        assert f.tags == []
        assert f.file_extension == []
        assert f.created_after is None
        assert f.created_before is None

    def test_source_filter_mapped(self) -> None:
        f = _map_filters({"source": ["folder", "confluence"]})
        assert f.source == ["folder", "confluence"]

    def test_file_type_mapped_to_mime_type(self) -> None:
        f = _map_filters({"file_type": ["application/pdf", "text/plain"]})
        assert f.mime_type == ["application/pdf", "text/plain"]

    def test_language_string_wrapped_in_list(self) -> None:
        f = _map_filters({"language": "he"})
        assert f.language == ["he"]

    def test_tags_mapped(self) -> None:
        f = _map_filters({"tags": ["contracts", "legal"]})
        assert f.tags == ["contracts", "legal"]

    def test_file_extension_mapped(self) -> None:
        f = _map_filters({"file_extension": [".pdf", ".docx"]})
        assert f.file_extension == [".pdf", ".docx"]

    def test_date_from_mapped_to_created_after(self) -> None:
        f = _map_filters({"date_from": "2025-01-01"})
        assert f.created_after == "2025-01-01"
        assert f.created_before is None

    def test_date_to_mapped_to_created_before(self) -> None:
        f = _map_filters({"date_to": "2025-12-31"})
        assert f.created_before == "2025-12-31"
        assert f.created_after is None

    def test_date_range_both_ends_mapped(self) -> None:
        f = _map_filters({"date_from": "2025-01-01", "date_to": "2025-12-31"})
        assert f.created_after == "2025-01-01"
        assert f.created_before == "2025-12-31"

    def test_non_string_language_ignored(self) -> None:
        f = _map_filters({"language": 42})
        assert f.language == []

    def test_empty_source_entries_filtered(self) -> None:
        f = _map_filters({"source": ["folder", "", None]})  # type: ignore[list-item]
        assert f.source == ["folder"]

    def test_non_list_source_ignored(self) -> None:
        f = _map_filters({"source": "folder"})
        assert f.source == []


# ---------------------------------------------------------------------------
# _qdrant_extra_conditions
# ---------------------------------------------------------------------------


class TestQdrantExtraConditions:
    def test_no_language_filter_returns_empty(self) -> None:
        f = _filters()
        conds = _qdrant_extra_conditions(f)
        assert conds == []

    def test_language_filter_produces_source_language_condition(self) -> None:
        f = _filters(language=["he"])
        conds = _qdrant_extra_conditions(f)
        assert len(conds) == 1
        cond = conds[0]
        assert isinstance(cond, FieldCondition)
        assert cond.key == "source_language"
        assert isinstance(cond.match, MatchAny)
        assert cond.match.any == ["he"]

    def test_multiple_languages_in_single_condition(self) -> None:
        f = _filters(language=["en", "he"])
        conds = _qdrant_extra_conditions(f)
        assert len(conds) == 1
        assert set(conds[0].match.any) == {"en", "he"}  # type: ignore[union-attr]

    def test_other_filters_do_not_produce_qdrant_conditions(self) -> None:
        f = _filters(source=["folder"], mime_type=["application/pdf"], tags=["legal"])
        conds = _qdrant_extra_conditions(f)
        assert conds == []


# ---------------------------------------------------------------------------
# _matches_filters — no-op for empty filters
# ---------------------------------------------------------------------------


class TestMatchesFiltersNoOp:
    def test_empty_filters_always_matches(self) -> None:
        doc = _doc()
        assert _matches_filters(doc, _filters()) is True

    def test_unfiltered_search_passes_any_doc(self) -> None:
        doc = _doc(source="confluence", mime_type="application/pdf", source_language="he")
        assert _matches_filters(doc, _filters()) is True


# ---------------------------------------------------------------------------
# _matches_filters — source filter
# ---------------------------------------------------------------------------


class TestMatchesFiltersSource:
    def test_source_match(self) -> None:
        doc = _doc(source="folder")
        assert _matches_filters(doc, _filters(source=["folder"])) is True

    def test_source_mismatch_excluded(self) -> None:
        doc = _doc(source="confluence")
        assert _matches_filters(doc, _filters(source=["folder"])) is False

    def test_source_any_of_list_matches(self) -> None:
        doc = _doc(source="jira")
        assert _matches_filters(doc, _filters(source=["folder", "jira"])) is True

    def test_empty_source_filter_is_noop(self) -> None:
        doc = _doc(source="confluence")
        assert _matches_filters(doc, _filters(source=[])) is True


# ---------------------------------------------------------------------------
# _matches_filters — MIME type filter
# ---------------------------------------------------------------------------


class TestMatchesFiltersMimeType:
    def test_mime_type_match(self) -> None:
        doc = _doc(mime_type="application/pdf")
        assert _matches_filters(doc, _filters(mime_type=["application/pdf"])) is True

    def test_mime_type_mismatch_excluded(self) -> None:
        doc = _doc(mime_type="text/plain")
        assert _matches_filters(doc, _filters(mime_type=["application/pdf"])) is False

    def test_mime_type_any_of_list(self) -> None:
        doc = _doc(mime_type="text/plain")
        assert _matches_filters(doc, _filters(mime_type=["application/pdf", "text/plain"])) is True


# ---------------------------------------------------------------------------
# _matches_filters — language filter
# ---------------------------------------------------------------------------


class TestMatchesFiltersLanguage:
    def test_language_match(self) -> None:
        doc = _doc(source_language="he")
        assert _matches_filters(doc, _filters(language=["he"])) is True

    def test_language_mismatch_excluded(self) -> None:
        doc = _doc(source_language="en")
        assert _matches_filters(doc, _filters(language=["he"])) is False

    def test_null_language_excluded_when_filter_set(self) -> None:
        doc = _doc(source_language=None)
        assert _matches_filters(doc, _filters(language=["en"])) is False

    def test_multiple_languages_any_match(self) -> None:
        doc = _doc(source_language="he")
        assert _matches_filters(doc, _filters(language=["en", "he"])) is True


# ---------------------------------------------------------------------------
# _matches_filters — tag filter
# ---------------------------------------------------------------------------


class TestMatchesFiltersTags:
    def test_tag_match(self) -> None:
        doc = _doc(metadata={"tags": ["contracts", "legal"]})
        assert _matches_filters(doc, _filters(tags=["legal"])) is True

    def test_tag_mismatch_excluded(self) -> None:
        doc = _doc(metadata={"tags": ["finance"]})
        assert _matches_filters(doc, _filters(tags=["legal"])) is False

    def test_any_tag_in_filter_matches(self) -> None:
        doc = _doc(metadata={"tags": ["legal"]})
        assert _matches_filters(doc, _filters(tags=["contracts", "legal"])) is True

    def test_string_tag_treated_as_single(self) -> None:
        doc = _doc(metadata={"tags": "legal"})
        assert _matches_filters(doc, _filters(tags=["legal"])) is True

    def test_missing_tags_excluded_when_filter_set(self) -> None:
        doc = _doc(metadata={})
        assert _matches_filters(doc, _filters(tags=["legal"])) is False

    def test_empty_tags_filter_is_noop(self) -> None:
        doc = _doc(metadata={"tags": ["legal"]})
        assert _matches_filters(doc, _filters(tags=[])) is True


# ---------------------------------------------------------------------------
# _matches_filters — file_extension filter
# ---------------------------------------------------------------------------


class TestMatchesFiltersFileExtension:
    def test_extension_match(self) -> None:
        doc = _doc(metadata={"file_extension": ".pdf"})
        assert _matches_filters(doc, _filters(file_extension=[".pdf"])) is True

    def test_extension_mismatch_excluded(self) -> None:
        doc = _doc(metadata={"file_extension": ".docx"})
        assert _matches_filters(doc, _filters(file_extension=[".pdf"])) is False

    def test_extension_case_insensitive(self) -> None:
        doc = _doc(metadata={"file_extension": ".PDF"})
        assert _matches_filters(doc, _filters(file_extension=[".pdf"])) is True

    def test_missing_extension_excluded_when_filter_set(self) -> None:
        doc = _doc(metadata={})
        assert _matches_filters(doc, _filters(file_extension=[".pdf"])) is False


# ---------------------------------------------------------------------------
# _matches_filters — date_from / created_after filter
# ---------------------------------------------------------------------------


class TestMatchesFiltersDateFrom:
    def test_doc_after_cutoff_passes(self) -> None:
        cutoff = datetime(2025, 6, 1, tzinfo=UTC)
        doc = _doc(created_at=cutoff + timedelta(days=1))
        assert _matches_filters(doc, _filters(created_after="2025-06-01")) is True

    def test_doc_exactly_at_cutoff_passes(self) -> None:
        cutoff = datetime(2025, 6, 1, tzinfo=UTC)
        doc = _doc(created_at=cutoff)
        assert _matches_filters(doc, _filters(created_after="2025-06-01T00:00:00")) is True

    def test_doc_before_cutoff_excluded(self) -> None:
        cutoff = datetime(2025, 6, 1, tzinfo=UTC)
        doc = _doc(created_at=cutoff - timedelta(days=1))
        assert _matches_filters(doc, _filters(created_after="2025-06-01")) is False

    def test_invalid_date_string_does_not_raise(self) -> None:
        doc = _doc()
        assert _matches_filters(doc, _filters(created_after="not-a-date")) is True


# ---------------------------------------------------------------------------
# _matches_filters — date_to / created_before filter
# ---------------------------------------------------------------------------


class TestMatchesFiltersDateTo:
    def test_doc_before_cutoff_passes(self) -> None:
        cutoff = datetime(2025, 12, 31, tzinfo=UTC)
        doc = _doc(created_at=cutoff - timedelta(days=1))
        assert _matches_filters(doc, _filters(created_before="2025-12-31")) is True

    def test_doc_exactly_at_cutoff_passes(self) -> None:
        cutoff = datetime(2025, 12, 31, tzinfo=UTC)
        doc = _doc(created_at=cutoff)
        assert _matches_filters(doc, _filters(created_before="2025-12-31T00:00:00")) is True

    def test_doc_after_cutoff_excluded(self) -> None:
        cutoff = datetime(2025, 12, 31, tzinfo=UTC)
        doc = _doc(created_at=cutoff + timedelta(days=1))
        assert _matches_filters(doc, _filters(created_before="2025-12-31")) is False

    def test_invalid_date_string_does_not_raise(self) -> None:
        doc = _doc()
        assert _matches_filters(doc, _filters(created_before="not-a-date")) is True

    def test_doc_created_during_boundary_day_passes(self) -> None:
        # Bare-date upper bound must include the whole calendar day, not just
        # its first instant: a doc created at 14:00 on the bound day is kept.
        doc = _doc(created_at=datetime(2025, 12, 31, 14, 0, tzinfo=UTC))
        assert _matches_filters(doc, _filters(created_before="2025-12-31")) is True

    def test_doc_at_start_of_next_day_excluded(self) -> None:
        doc = _doc(created_at=datetime(2026, 1, 1, 0, 0, tzinfo=UTC))
        assert _matches_filters(doc, _filters(created_before="2025-12-31")) is False

    def test_invalid_after_does_not_disable_before_filter(self) -> None:
        # A malformed created_after bound must not short-circuit the predicate
        # and silently drop a valid created_before filter.
        doc = _doc(created_at=datetime(2026, 6, 1, tzinfo=UTC))
        f = _filters(created_after="garbage", created_before="2025-12-31")
        assert _matches_filters(doc, f) is False

    def test_date_range_both_bounds(self) -> None:
        doc_in = _doc(created_at=datetime(2025, 6, 15, tzinfo=UTC))
        doc_before = _doc(created_at=datetime(2025, 1, 1, tzinfo=UTC))
        doc_after = _doc(created_at=datetime(2025, 12, 31, tzinfo=UTC))
        f = _filters(created_after="2025-06-01", created_before="2025-11-30")
        assert _matches_filters(doc_in, f) is True
        assert _matches_filters(doc_before, f) is False
        assert _matches_filters(doc_after, f) is False

    def test_naive_datetime_treated_as_utc(self) -> None:
        naive_dt = datetime(2025, 6, 1)  # no tzinfo
        doc = _doc(created_at=naive_dt)
        assert _matches_filters(doc, _filters(created_before="2025-12-31")) is True

    def test_tz_aware_datetime_in_filter(self) -> None:
        doc = _doc(created_at=datetime(2025, 6, 1, tzinfo=UTC))
        # Filter string with +02:00 offset; fromisoformat normalises to UTC
        f = _filters(created_before="2025-07-01T00:00:00+02:00")
        assert _matches_filters(doc, f) is True


# ---------------------------------------------------------------------------
# Hybrid scenarios: vector-only and BM25-only out-of-filter leaks
# ---------------------------------------------------------------------------


class TestMatchesFiltersHybridScenarios:
    """Simulate what the search route does: build all_docs, then apply _matches_filters.

    The search router merges BM25 + vector results, loads DocumentRows, and
    applies _matches_filters to the merged list.  These tests verify that a
    result present from one backend but not matching the filter is excluded.
    """

    def test_vector_only_result_excluded_by_source_filter(self) -> None:
        """A Qdrant hit from source 'confluence' is excluded when filter=folder."""
        doc = _doc(source="confluence")
        f = _filters(source=["folder"])
        assert _matches_filters(doc, f) is False

    def test_bm25_only_result_excluded_by_mime_filter(self) -> None:
        """A Meilisearch hit with mime text/plain excluded when filter=application/pdf."""
        doc = _doc(mime_type="text/plain")
        f = _filters(mime_type=["application/pdf"])
        assert _matches_filters(doc, f) is False

    def test_vector_result_excluded_by_language_filter(self) -> None:
        """A vector result in English is excluded when filter=he."""
        doc = _doc(source_language="en")
        f = _filters(language=["he"])
        assert _matches_filters(doc, f) is False

    def test_bm25_result_excluded_by_tag_filter(self) -> None:
        """A BM25 hit without the required tag is excluded."""
        doc = _doc(metadata={"tags": ["finance"]})
        f = _filters(tags=["legal"])
        assert _matches_filters(doc, f) is False

    def test_vector_result_excluded_by_date_filter(self) -> None:
        """A Qdrant hit older than date_from is excluded."""
        old = datetime(2024, 1, 1, tzinfo=UTC)
        doc = _doc(created_at=old)
        f = _filters(created_after="2025-01-01")
        assert _matches_filters(doc, f) is False

    def test_vector_result_excluded_by_date_to(self) -> None:
        """A Qdrant hit newer than date_to is excluded (fixes the date_to backend gap)."""
        future = datetime(2026, 6, 1, tzinfo=UTC)
        doc = _doc(created_at=future)
        f = _filters(created_before="2025-12-31")
        assert _matches_filters(doc, f) is False

    def test_bm25_result_passes_all_filters(self) -> None:
        """A BM25 result matching all filters is kept."""
        doc = _doc(
            source="folder",
            mime_type="application/pdf",
            source_language="en",
            metadata={"tags": ["legal"], "file_extension": ".pdf"},
            created_at=datetime(2025, 6, 15, tzinfo=UTC),
        )
        f = _filters(
            source=["folder"],
            mime_type=["application/pdf"],
            language=["en"],
            tags=["legal"],
            file_extension=[".pdf"],
            created_after="2025-01-01",
            created_before="2025-12-31",
        )
        assert _matches_filters(doc, f) is True

    def test_empty_result_when_all_candidates_filtered(self) -> None:
        """No results survive when every candidate fails at least one filter."""
        docs = [
            _doc(source="confluence"),  # source filter excludes this
            _doc(mime_type="text/html"),  # mime filter excludes this
        ]
        f = _filters(source=["folder"], mime_type=["application/pdf"])
        surviving = [d for d in docs if _matches_filters(d, f)]
        assert surviving == []

    def test_mixed_results_only_matching_survive(self) -> None:
        """Only docs that satisfy all filters are kept."""
        good = _doc(source="folder", mime_type="application/pdf", source_language="en")
        bad_source = _doc(source="confluence", mime_type="application/pdf", source_language="en")
        bad_lang = _doc(source="folder", mime_type="application/pdf", source_language="he")
        f = _filters(source=["folder"], mime_type=["application/pdf"], language=["en"])
        surviving = [d for d in [good, bad_source, bad_lang] if _matches_filters(d, f)]
        assert len(surviving) == 1
        assert surviving[0] is good
