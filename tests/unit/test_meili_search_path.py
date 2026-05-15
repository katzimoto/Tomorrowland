"""Tests for the Meilisearch search path — settings and attribute coverage."""

from __future__ import annotations

from services.search.meili_settings import (
    _FILTERABLE_ATTRIBUTES as FILTERABLE_ATTRIBUTES,
)
from services.search.meili_settings import (
    _SEARCHABLE_ATTRIBUTES as SEARCHABLE_ATTRIBUTES,
)
from services.search.meili_settings import (
    _SORTABLE_ATTRIBUTES as SORTABLE_ATTRIBUTES,
)
from services.search.meili_settings import (
    INDEX_NAME,
)


class TestMeiliSettings:
    """Tests that searchable attributes cover expected fields."""

    def test_searchable_attributes_include_content(self):
        assert "content_en" in SEARCHABLE_ATTRIBUTES
        assert "content_he" in SEARCHABLE_ATTRIBUTES

    def test_searchable_attributes_include_title(self):
        assert "title" in SEARCHABLE_ATTRIBUTES
        assert "title_en" in SEARCHABLE_ATTRIBUTES
        assert "title_he" in SEARCHABLE_ATTRIBUTES

    def test_searchable_attributes_include_metadata(self):
        assert "description" in SEARCHABLE_ATTRIBUTES
        assert "subtitle" in SEARCHABLE_ATTRIBUTES

    def test_filterable_attributes_include_acl(self):
        assert "allowed_group_ids" in FILTERABLE_ATTRIBUTES
        assert "document_id" in FILTERABLE_ATTRIBUTES

    def test_filterable_attributes_include_metadata_fields(self):
        assert "metadata.source" in FILTERABLE_ATTRIBUTES
        assert "metadata.mime_type" in FILTERABLE_ATTRIBUTES
        assert "metadata.language" in FILTERABLE_ATTRIBUTES
        assert "metadata.tags" in FILTERABLE_ATTRIBUTES

    def test_sortable_attributes_exist(self):
        assert len(SORTABLE_ATTRIBUTES) > 0
        assert "chunk_index" in SORTABLE_ATTRIBUTES

    def test_index_name_is_document_index(self):
        assert INDEX_NAME == "documents"

    def test_no_unsafe_metadata_fields_in_filterable(self):
        unsafe = {"password", "secret", "token", "api_key", "private_key"}
        for attr in FILTERABLE_ATTRIBUTES:
            for u in unsafe:
                assert u not in attr.lower(), f"Filterable attr contains unsafe field: {attr}"
