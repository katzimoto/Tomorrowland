from __future__ import annotations

from typing import Any

INDEX_NAME = "documents"
SHADOW_INDEX_NAME = "documents_shadow"

SETTINGS_VERSION = 1

# ---------------------------------------------------------------------------
# Searchable attributes
# ---------------------------------------------------------------------------
# Order determines attribute weight in the `attribute` ranking rule.
# Earlier position = stronger boost when a query term matches there.
_SEARCHABLE_ATTRIBUTES: list[str] = [
    # Title — highest weight
    "title",
    "title_en",
    "title_he",
    # Section headings
    "heading",
    "heading_en",
    "heading_he",
    # Structural overview
    "subtitle",
    "description",
    # Chunk body — core match field
    "content",
    "content_en",
    "content_he",
    # Generated summaries
    "summary",
    "summary_en",
    "summary_he",
    # Document hierarchy
    "section_path",
    # Catch-all metadata blob (allowlisted — see build_metadata_text)
    "metadata_text",
    # Individual metadata fields that benefit from text search
    "metadata.file_name",
    "metadata.path",
    "metadata.url",
    "metadata.author",
    "metadata.owner",
    "metadata.tags",
    "metadata.labels",
    "metadata.topics",
    "metadata.project",
    "metadata.workspace",
    "metadata.collection",
]

# ---------------------------------------------------------------------------
# Filterable attributes
# ---------------------------------------------------------------------------
# allowed_group_ids and is_admin_only are REQUIRED — they back the ACL filter
# applied on every query. Never remove them.
_FILTERABLE_ATTRIBUTES: list[str] = [
    "document_id",
    "allowed_group_ids",  # ACL — required on every query
    "is_admin_only",
    "chunk_index",
    "metadata.source",
    "metadata.document_type",
    "metadata.mime_type",
    "metadata.file_extension",
    "metadata.language",
    "metadata.author",
    "metadata.owner",
    "metadata.tags",
    "metadata.labels",
    "metadata.topics",
    "metadata.project",
    "metadata.workspace",
    "metadata.collection",
    "metadata.created_at",
    "metadata.updated_at",
    "metadata.imported_at",
    # Intentionally excluded: metadata.checksum, metadata.version (internal fields)
]

# ---------------------------------------------------------------------------
# Sortable attributes
# ---------------------------------------------------------------------------
_SORTABLE_ATTRIBUTES: list[str] = [
    "metadata.created_at",
    "metadata.updated_at",
    "metadata.imported_at",
    "chunk_index",
    "position.page_number",
]

# ---------------------------------------------------------------------------
# Ranking rules
# ---------------------------------------------------------------------------
# Meilisearch defaults. The attribute rule amplifies title/heading matches
# over content matches based on searchable_attributes order above.
_RANKING_RULES: list[str] = [
    "words",
    "typo",
    "proximity",
    "attribute",
    "sort",
    "exactness",
]

# ---------------------------------------------------------------------------
# Stop words
# ---------------------------------------------------------------------------
_STOP_WORDS: list[str] = [
    # English
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "in",
    "to",
    "for",
    "is",
    "it",
    "on",
    "at",
    "by",
    "with",
    "from",
    "as",
    # Hebrew — high-frequency particles that carry no discriminating search value
    "של",  # of / belonging to
    "עם",  # with
    "את",  # accusative marker / you (f.)
    "הם",  # they (m.)
    "הן",  # they (f.)
    "הוא",  # he
    "היא",  # she
    "אני",  # I
    "אתה",  # you (m.)
    "כי",  # because / that
    "לא",  # not / no
    "על",  # on / about
    "אל",  # to / don't
    "גם",  # also
    "רק",  # only
    "כל",  # all / every
    "זה",  # this (m.)
    "זו",  # this (f.)
    "אנחנו",  # we
    "אבל",  # but
    "לו",  # to him
    "לה",  # to her
    "אם",  # if
    "כאשר",  # when
    "אשר",  # which / that
    "כך",  # thus / so
    "כבר",  # already
    "עוד",  # still / more
    "כאן",  # here
    "יש",  # there is
    "אין",  # there is not
    "מה",  # what
    "מי",  # who
    "איך",  # how
    "מתי",  # when (time)
    "לפני",  # before
    "אחרי",  # after
    "בין",  # between
]

# ---------------------------------------------------------------------------
# Synonyms
# ---------------------------------------------------------------------------
_SYNONYMS: dict[str, list[str]] = {
    "spec": ["specification", "specifications"],
    "prd": ["product requirements", "requirements document"],
    "design": ["design doc", "design document"],
    "notes": ["meeting notes", "meeting minutes"],
    "transcript": ["meeting transcript", "call transcript", "recording transcript"],
}

# ---------------------------------------------------------------------------
# Typo tolerance
# ---------------------------------------------------------------------------
_TYPO_TOLERANCE: dict[str, Any] = {
    "enabled": True,
    "minWordSizeForTypos": {
        "oneTypo": 5,
        "twoTypos": 9,
    },
    # Exact-match fields — typos produce wrong filters, not fuzzy matches
    "disableOnAttributes": [
        "metadata.tags",
        "metadata.labels",
        "metadata.collection",
        "allowed_group_ids",
    ],
}

# ---------------------------------------------------------------------------
# Faceting
# ---------------------------------------------------------------------------
_FACETING: dict[str, Any] = {
    "maxValuesPerFacet": 100,
    "sortFacetValuesBy": {"*": "count"},
}

# ---------------------------------------------------------------------------
# Displayed attributes
# ---------------------------------------------------------------------------
# Excluded: allowed_group_ids, is_admin_only, content_checksum, indexed_at,
# metadata.checksum, metadata.version, metadata.path, metadata.url,
# metadata_text (catch-all blob — snippets come from individual content fields)
_DISPLAYED_ATTRIBUTES: list[str] = [
    "id",
    "document_id",
    "chunk_index",
    "title",
    "title_en",
    "title_he",
    "heading",
    "heading_en",
    "heading_he",
    "subtitle",
    "description",
    "content",
    "content_en",
    "content_he",
    "summary",
    "summary_en",
    "summary_he",
    "section_path",
    "position",
    "metadata.source",
    "metadata.document_type",
    "metadata.mime_type",
    "metadata.file_name",
    "metadata.file_extension",
    "metadata.language",
    "metadata.author",
    "metadata.owner",
    "metadata.tags",
    "metadata.labels",
    "metadata.topics",
    "metadata.project",
    "metadata.workspace",
    "metadata.collection",
    "metadata.created_at",
    "metadata.updated_at",
    "metadata.imported_at",
]

# ---------------------------------------------------------------------------
# Assembled settings object
# ---------------------------------------------------------------------------
INDEX_SETTINGS: dict[str, Any] = {
    "searchableAttributes": _SEARCHABLE_ATTRIBUTES,
    "filterableAttributes": _FILTERABLE_ATTRIBUTES,
    "sortableAttributes": _SORTABLE_ATTRIBUTES,
    "rankingRules": _RANKING_RULES,
    "distinctAttribute": "document_id",
    "stopWords": _STOP_WORDS,
    "synonyms": _SYNONYMS,
    "typoTolerance": _TYPO_TOLERANCE,
    "faceting": _FACETING,
    "displayedAttributes": _DISPLAYED_ATTRIBUTES,
}


def apply_index_settings(client: Any, *, shadow: bool = False) -> None:
    """Apply INDEX_SETTINGS to the live index (or shadow index if shadow=True).

    Creates the index if it does not exist. Safe to call on every startup —
    Meilisearch applies settings as a task and does not drop existing documents.

    Args:
        client: A meilisearch.Client instance.
        shadow: When True, targets SHADOW_INDEX_NAME instead of INDEX_NAME.
    """
    name = SHADOW_INDEX_NAME if shadow else INDEX_NAME
    existing = [idx.uid for idx in client.get_indexes()["results"]]
    if name not in existing:
        client.create_index(name, {"primaryKey": "id"})
    client.index(name).update_settings(INDEX_SETTINGS)
