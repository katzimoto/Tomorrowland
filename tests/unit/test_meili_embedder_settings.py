"""Unit tests for Meilisearch embedder settings and hybrid config."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from services.search.meili_settings import (
    EMBEDDER_DOCUMENT_TEMPLATE,
    INDEX_NAME,
    apply_index_settings,
)


def _make_client(existing_indexes: list[str] | None = None) -> MagicMock:
    """Return a mock meilisearch.Client with minimal plumbing."""
    client = MagicMock()
    idx_objs = [MagicMock(uid=name) for name in (existing_indexes or [INDEX_NAME])]
    client.get_indexes.return_value = {"results": idx_objs}
    return client


class TestApplyIndexSettingsHybridFalse:
    def test_no_embedders_key(self) -> None:
        client = _make_client()
        apply_index_settings(client, hybrid=False)
        settings_applied = client.index(INDEX_NAME).update_settings.call_args[0][0]
        assert "embedders" not in settings_applied

    def test_no_vector_ranking_rule(self) -> None:
        client = _make_client()
        apply_index_settings(client, hybrid=False)
        settings_applied = client.index(INDEX_NAME).update_settings.call_args[0][0]
        assert "vector" not in settings_applied.get("rankingRules", [])


class TestApplyIndexSettingsHybridTrue:
    def _settings(self, **kwargs: object) -> dict:
        client = _make_client()
        apply_index_settings(
            client,
            hybrid=True,
            embedding_url="http://ollama-embed:11434/api/embed",
            embedding_model="nomic-embed-text",
            embedding_dimension=768,
            embedder_name="default",
            **kwargs,
        )
        return client.index(INDEX_NAME).update_settings.call_args[0][0]

    def test_embedders_block_present(self) -> None:
        s = self._settings()
        assert "embedders" in s

    def test_embedder_source_is_ollama(self) -> None:
        s = self._settings()
        assert s["embedders"]["default"]["source"] == "ollama"

    def test_embedder_url(self) -> None:
        s = self._settings()
        assert s["embedders"]["default"]["url"] == "http://ollama-embed:11434/api/embed"

    def test_embedder_model(self) -> None:
        s = self._settings()
        assert s["embedders"]["default"]["model"] == "nomic-embed-text"

    def test_embedder_dimensions(self) -> None:
        s = self._settings()
        assert s["embedders"]["default"]["dimensions"] == 768

    def test_document_template_stable(self) -> None:
        """documentTemplate must not change — doing so invalidates all vectors."""
        s = self._settings()
        assert s["embedders"]["default"]["documentTemplate"] == EMBEDDER_DOCUMENT_TEMPLATE

    def test_vector_appended_to_ranking_rules(self) -> None:
        s = self._settings()
        assert "vector" in s["rankingRules"]

    def test_vector_is_last_ranking_rule(self) -> None:
        """vector rule should come after all BM25 rules."""
        s = self._settings()
        assert s["rankingRules"][-1] == "vector"

    def test_custom_embedder_name(self) -> None:
        client = _make_client()
        apply_index_settings(
            client,
            hybrid=True,
            embedding_url="http://x:11434/api/embed",
            embedder_name="my-embedder",
        )
        s = client.index(INDEX_NAME).update_settings.call_args[0][0]
        assert "my-embedder" in s["embedders"]
        assert "default" not in s["embedders"]

    def test_original_index_settings_not_mutated(self) -> None:
        """apply_index_settings must not mutate the module-level INDEX_SETTINGS dict."""
        from services.search.meili_settings import INDEX_SETTINGS

        original_rules = list(INDEX_SETTINGS.get("rankingRules", []))
        client = _make_client()
        apply_index_settings(client, hybrid=True)
        assert INDEX_SETTINGS.get("rankingRules") == original_rules
        assert "embedders" not in INDEX_SETTINGS
