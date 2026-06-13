from __future__ import annotations

from unittest.mock import MagicMock

from services.search.meili_settings import (
    INDEX_NAME,
    INDEX_SETTINGS,
    SETTINGS_VERSION,
    SHADOW_INDEX_NAME,
)

_REQUIRED_TOP_LEVEL_KEYS = {
    "searchableAttributes",
    "filterableAttributes",
    "sortableAttributes",
    "rankingRules",
    "distinctAttribute",
    "stopWords",
    "synonyms",
    "typoTolerance",
    "faceting",
    "displayedAttributes",
}


def test_index_name_is_documents() -> None:
    assert INDEX_NAME == "documents"


def test_shadow_index_name_differs_from_live() -> None:
    assert SHADOW_INDEX_NAME != INDEX_NAME
    assert "shadow" in SHADOW_INDEX_NAME


def test_settings_version_is_positive_int() -> None:
    assert isinstance(SETTINGS_VERSION, int)
    assert SETTINGS_VERSION >= 1


def test_settings_contains_all_required_keys() -> None:
    assert set(INDEX_SETTINGS.keys()) >= _REQUIRED_TOP_LEVEL_KEYS


def test_apply_index_settings_creates_index_then_applies_settings() -> None:
    """apply_index_settings must call create_index (when missing) AND
    update_settings, and return both task UIDs.
    """
    from services.search.meili_settings import apply_index_settings

    client = MagicMock()
    client.get_indexes.return_value = {"results": []}  # no pre-existing index
    create_task = MagicMock(task_uid=11)
    settings_task = MagicMock(task_uid=22)
    client.create_index.return_value = create_task
    client.index.return_value.update_settings.return_value = settings_task

    uids = apply_index_settings(client, shadow=False)

    client.create_index.assert_called_once()
    client.index.assert_called_with("documents")
    assert uids == ["11", "22"]


def test_apply_index_settings_targets_shadow_index() -> None:
    from services.search.meili_settings import apply_index_settings

    client = MagicMock()
    client.get_indexes.return_value = {"results": []}
    create_task = MagicMock(task_uid=33)
    settings_task = MagicMock(task_uid=44)
    client.create_index.return_value = create_task
    client.index.return_value.update_settings.return_value = settings_task

    apply_index_settings(client, shadow=True)

    client.create_index.assert_called_once()
    # First positional arg is the shadow index name
    assert client.index.call_args[0][0] == "documents_shadow"


def test_distinct_attribute_is_document_id() -> None:
    assert INDEX_SETTINGS["distinctAttribute"] == "document_id"


# ---------------------------------------------------------------------------
# Filterable attributes — security invariants
# ---------------------------------------------------------------------------


def test_allowed_group_ids_is_filterable() -> None:
    assert "allowed_group_ids" in INDEX_SETTINGS["filterableAttributes"]


def test_is_admin_only_is_filterable() -> None:
    assert "is_admin_only" in INDEX_SETTINGS["filterableAttributes"]


def test_metadata_source_id_is_filterable() -> None:
    assert "metadata.source_id" in INDEX_SETTINGS["filterableAttributes"]


def test_metadata_source_id_is_displayed() -> None:
    assert "metadata.source_id" in INDEX_SETTINGS["displayedAttributes"]


def test_metadata_checksum_not_filterable() -> None:
    assert "metadata.checksum" not in INDEX_SETTINGS["filterableAttributes"]


def test_metadata_version_not_filterable() -> None:
    assert "metadata.version" not in INDEX_SETTINGS["filterableAttributes"]


# ---------------------------------------------------------------------------
# Displayed attributes — security invariants
# ---------------------------------------------------------------------------


def test_allowed_group_ids_not_displayed() -> None:
    assert "allowed_group_ids" not in INDEX_SETTINGS["displayedAttributes"]


def test_is_admin_only_not_displayed() -> None:
    assert "is_admin_only" not in INDEX_SETTINGS["displayedAttributes"]


def test_content_checksum_not_displayed() -> None:
    assert "content_checksum" not in INDEX_SETTINGS["displayedAttributes"]


def test_indexed_at_not_displayed() -> None:
    assert "indexed_at" not in INDEX_SETTINGS["displayedAttributes"]


def test_metadata_checksum_not_displayed() -> None:
    assert "metadata.checksum" not in INDEX_SETTINGS["displayedAttributes"]


def test_metadata_path_not_displayed() -> None:
    assert "metadata.path" not in INDEX_SETTINGS["displayedAttributes"]


# ---------------------------------------------------------------------------
# Stop words
# ---------------------------------------------------------------------------


def test_stop_words_is_non_empty() -> None:
    assert len(INDEX_SETTINGS["stopWords"]) > 0


def test_stop_words_includes_hebrew_particles() -> None:
    stop_words = INDEX_SETTINGS["stopWords"]
    # Most common Hebrew stop words that must be present
    for word in ("של", "עם", "את", "לא"):
        assert word in stop_words, f"Hebrew stop word {word!r} missing"


def test_stop_words_includes_english_articles() -> None:
    stop_words = INDEX_SETTINGS["stopWords"]
    for word in ("a", "an", "the"):
        assert word in stop_words, f"English stop word {word!r} missing"


# ---------------------------------------------------------------------------
# Searchable attributes — key fields present
# ---------------------------------------------------------------------------


def test_title_is_searchable() -> None:
    assert "title" in INDEX_SETTINGS["searchableAttributes"]


def test_content_fields_searchable() -> None:
    sa = INDEX_SETTINGS["searchableAttributes"]
    assert "content" in sa
    assert "content_en" in sa
    assert "content_he" in sa


def test_title_before_content_in_searchable_attributes() -> None:
    sa = INDEX_SETTINGS["searchableAttributes"]
    assert sa.index("title") < sa.index("content")


def test_metadata_text_is_searchable() -> None:
    assert "metadata_text" in INDEX_SETTINGS["searchableAttributes"]


# ---------------------------------------------------------------------------
# Ranking rules
# ---------------------------------------------------------------------------


def test_ranking_rules_present_and_ordered() -> None:
    rules = INDEX_SETTINGS["rankingRules"]
    assert rules[0] == "words"
    assert "attribute" in rules
