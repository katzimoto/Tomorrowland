from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.search.meili_provider import MeilisearchSearchProvider


def _client_with_task_uids(task_uids: list[int]) -> MagicMock:
    """Build a mock meilisearch client whose apply_index_settings chain
    returns the given task UID list. The chain is:
        get_indexes -> create_index (optional) -> index().update_settings
    """
    client = MagicMock()
    client.get_indexes.return_value = {"results": []}  # no pre-existing index
    create_task = MagicMock(task_uid=task_uids[0]) if task_uids else MagicMock()
    settings_task = MagicMock(task_uid=task_uids[1] if len(task_uids) > 1 else 999)
    client.create_index.return_value = create_task
    client.index.return_value.update_settings.return_value = settings_task
    return client


def _provider_with_pending_uids() -> tuple[MagicMock, MeilisearchSearchProvider]:
    client = _client_with_task_uids([101, 202])
    provider = MeilisearchSearchProvider(client)
    return client, provider


# ---------------------------------------------------------------------------
# __init__ captures settings task UIDs
# ---------------------------------------------------------------------------


def test_init_captures_create_index_and_update_settings_task_uids() -> None:
    client = _client_with_task_uids([101, 202])
    provider = MeilisearchSearchProvider(client)
    assert provider._initial_settings_task_uids == ["101", "202"]


def test_init_skips_create_index_when_index_exists() -> None:
    client = MagicMock()
    client.get_indexes.return_value = {"results": [MagicMock(uid="documents")]}
    settings_task = MagicMock(task_uid=303)
    client.index.return_value.update_settings.return_value = settings_task
    provider = MeilisearchSearchProvider(client)
    # No create_index call → only the update_settings task UID is captured
    assert provider._initial_settings_task_uids == ["303"]


# ---------------------------------------------------------------------------
# await_initial_settings
# ---------------------------------------------------------------------------


def test_wait_for_initial_settings_calls_wait_for_task_per_uid() -> None:
    client, provider = _provider_with_pending_uids()
    with patch.object(provider, "wait_for_task") as mock_wait:
        provider.wait_for_initial_settings(timeout_seconds=5.0, poll_interval_seconds=0.1)
    assert mock_wait.call_count == 2
    # Tasks must be waited on in submission order
    assert [c.args[0] for c in mock_wait.call_args_list] == ["101", "202"]


def test_wait_for_initial_settings_propagates_timeout_error() -> None:
    client, provider = _provider_with_pending_uids()

    def _raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise TimeoutError("not ready in time")

    with patch.object(provider, "wait_for_task", side_effect=_raise), pytest.raises(TimeoutError):
        provider.wait_for_initial_settings(timeout_seconds=1.0, poll_interval_seconds=0.01)


def test_wait_for_initial_settings_propagates_runtime_error_on_failed_task() -> None:
    client, provider = _provider_with_pending_uids()

    def _raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("task failed: invalid settings")

    with (
        patch.object(provider, "wait_for_task", side_effect=_raise),
        pytest.raises(RuntimeError, match="task failed"),
    ):
        provider.wait_for_initial_settings(timeout_seconds=1.0, poll_interval_seconds=0.01)


def test_wait_for_initial_settings_noop_when_no_pending() -> None:
    """A fresh provider whose index already existed has only the
    update_settings task — verify the list is non-empty but the call
    iterates it cleanly with no errors.
    """
    client = MagicMock()
    client.get_indexes.return_value = {"results": [MagicMock(uid="documents")]}
    settings_task = MagicMock(task_uid=303)
    client.index.return_value.update_settings.return_value = settings_task
    provider = MeilisearchSearchProvider(client)
    with patch.object(provider, "wait_for_task") as mock_wait:
        provider.wait_for_initial_settings(timeout_seconds=1.0, poll_interval_seconds=0.01)
    mock_wait.assert_called_once_with("303", timeout_seconds=1.0, poll_interval_seconds=0.01)


# ---------------------------------------------------------------------------
# apply_settings appends to the tracked list
# ---------------------------------------------------------------------------


def test_apply_settings_appends_to_tracked_task_uids() -> None:
    """A subsequent apply_settings call must add a new task UID (create +
    update) to the tracked list so wait_for_initial_settings waits on it.
    """
    client, provider = _provider_with_pending_uids()
    assert provider._initial_settings_task_uids == ["101", "202"]

    # Swap both chains so the second apply emits distinct task UIDs
    client.create_index.return_value = MagicMock(task_uid=303)
    client.index.return_value.update_settings.return_value = MagicMock(task_uid=505)
    provider.apply_settings()
    assert provider._initial_settings_task_uids == ["101", "202", "303", "505"]


# ---------------------------------------------------------------------------
# apply_index_settings returns task UIDs
# ---------------------------------------------------------------------------


def test_apply_index_settings_returns_two_task_uids_when_index_created() -> None:
    from services.search.meili_settings import apply_index_settings

    client = _client_with_task_uids([11, 22])
    uids = apply_index_settings(client, shadow=False)
    assert uids == ["11", "22"]


def test_apply_index_settings_returns_one_task_uid_when_index_exists() -> None:
    from services.search.meili_settings import apply_index_settings

    client = MagicMock()
    client.get_indexes.return_value = {"results": [MagicMock(uid="documents")]}
    client.index.return_value.update_settings.return_value = MagicMock(task_uid=33)
    uids = apply_index_settings(client, shadow=False)
    assert uids == ["33"]


# ---------------------------------------------------------------------------
# initialize_meilisearch returns the union of task UIDs
# ---------------------------------------------------------------------------


def test_initialize_meilisearch_returns_live_only_when_shadow_disabled() -> None:
    from services.search.meili_rollout import initialize_meilisearch

    client = MagicMock()
    client.get_indexes.return_value = {"results": []}
    # The first call (shadow=False) needs to be tracked; we can ignore shadow
    client.create_index.return_value = MagicMock(task_uid=1)
    client.index.return_value.update_settings.return_value = MagicMock(task_uid=2)

    settings = MagicMock()
    settings.feature_meilisearch_search = True
    settings.feature_meilisearch_shadow_index = False

    uids = initialize_meilisearch(client, settings)
    assert uids == ["1", "2"]


def test_initialize_meilisearch_returns_live_and_shadow_when_enabled() -> None:
    from services.search.meili_rollout import initialize_meilisearch

    client = MagicMock()
    client.get_indexes.return_value = {"results": []}
    # Live: 1+2, shadow: 3+4
    client.create_index.side_effect = [
        MagicMock(task_uid=1),
        MagicMock(task_uid=3),
    ]
    client.index.return_value.update_settings.side_effect = [
        MagicMock(task_uid=2),
        MagicMock(task_uid=4),
    ]

    settings = MagicMock()
    settings.feature_meilisearch_search = True
    settings.feature_meilisearch_shadow_index = True

    uids = initialize_meilisearch(client, settings)
    assert uids == ["1", "2", "3", "4"]
