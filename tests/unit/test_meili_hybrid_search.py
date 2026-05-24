"""Unit tests for hybrid query parameter in MeilisearchSearchProvider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_provider(hybrid: bool = False, semantic_ratio: float = 0.5):
    """Return a MeilisearchSearchProvider with a mock client."""
    from services.search.meili_provider import MeilisearchSearchProvider

    client = MagicMock()
    client.get_indexes.return_value = {"results": [MagicMock(uid="documents")]}
    client.index.return_value.search.return_value = {"hits": []}

    return MeilisearchSearchProvider(
        client=client,
        hybrid=hybrid,
        embedder_name="default",
        semantic_ratio=semantic_ratio,
    )


def _last_search_params(provider) -> dict:
    """Return the params dict from the last search() SDK call."""
    calls = provider._client.index.return_value.search.call_args_list
    assert calls, "search was never called"
    # search(query, params) — params is second positional arg
    return calls[-1][0][1]


class TestHybridFalse:
    def _search(self, provider):
        from services.search.meili_types import DocumentSearchQuery

        user = MagicMock()
        user.groups = ["g1"]
        user.is_admin = True

        with patch("services.search.meili_provider.needs_acl_short_circuit", return_value=False), \
             patch("services.search.meili_provider.build_permission_filter", return_value=""), \
             patch("services.search.meili_provider.compose_filters", return_value=""):
            provider.search(DocumentSearchQuery(q="hello"), user)

    def test_no_hybrid_key_when_disabled(self) -> None:
        provider = _make_provider(hybrid=False)
        self._search(provider)
        params = _last_search_params(provider)
        assert "hybrid" not in params


class TestHybridTrue:
    def _search(self, provider, query: str = "hello"):
        from services.search.meili_types import DocumentSearchQuery

        user = MagicMock()
        user.groups = ["g1"]
        user.is_admin = True

        with patch("services.search.meili_provider.needs_acl_short_circuit", return_value=False), \
             patch("services.search.meili_provider.build_permission_filter", return_value=""), \
             patch("services.search.meili_provider.compose_filters", return_value=""):
            provider.search(DocumentSearchQuery(q=query), user)

    def test_hybrid_key_present(self) -> None:
        provider = _make_provider(hybrid=True)
        self._search(provider)
        params = _last_search_params(provider)
        assert "hybrid" in params

    def test_embedder_name(self) -> None:
        provider = _make_provider(hybrid=True)
        self._search(provider)
        params = _last_search_params(provider)
        assert params["hybrid"]["embedder"] == "default"

    def test_semantic_ratio_default(self) -> None:
        provider = _make_provider(hybrid=True, semantic_ratio=0.5)
        self._search(provider)
        params = _last_search_params(provider)
        assert params["hybrid"]["semanticRatio"] == 0.5

    def test_semantic_ratio_custom(self) -> None:
        provider = _make_provider(hybrid=True, semantic_ratio=0.7)
        self._search(provider)
        params = _last_search_params(provider)
        assert params["hybrid"]["semanticRatio"] == 0.7
