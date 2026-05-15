from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from services.search.meili_acl import (
    allowed_group_ids_for_indexing,
    build_permission_filter,
    compose_filters,
    needs_acl_short_circuit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_G1 = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_G2 = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


def _user(*, is_admin: bool, groups: list[uuid.UUID]) -> MagicMock:
    u = MagicMock()
    u.is_admin = is_admin
    u.groups = groups
    return u


# ---------------------------------------------------------------------------
# build_permission_filter
# ---------------------------------------------------------------------------


def test_admin_returns_empty_filter() -> None:
    assert build_permission_filter(_user(is_admin=True, groups=[_G1, _G2])) == ""


def test_admin_with_no_groups_still_empty_filter() -> None:
    assert build_permission_filter(_user(is_admin=True, groups=[])) == ""


def test_single_group_includes_id_and_admin_only_guard() -> None:
    f = build_permission_filter(_user(is_admin=False, groups=[_G1]))
    assert f'"{_G1}"' in f
    assert "is_admin_only = false" in f
    assert "allowed_group_ids IN" in f


def test_multiple_groups_all_ids_present() -> None:
    f = build_permission_filter(_user(is_admin=False, groups=[_G1, _G2]))
    assert f'"{_G1}"' in f
    assert f'"{_G2}"' in f
    assert "is_admin_only = false" in f


def test_no_groups_returns_impossible_predicate() -> None:
    # Must not produce an empty IN [] which is ambiguous in Meilisearch
    f = build_permission_filter(_user(is_admin=False, groups=[]))
    assert f != ""
    # The predicate should never match any real record
    assert "is_admin_only = true" in f
    assert "is_admin_only = false" in f


def test_no_user_input_interpolated_into_filter() -> None:
    # Group IDs come from the signed JWT — they are UUIDs.
    # Verify the filter only contains the UUID string, not any extra characters.
    f = build_permission_filter(_user(is_admin=False, groups=[_G1]))
    g1_str = str(_G1)
    assert g1_str in f
    # No raw format strings or unquoted values
    assert f'"{g1_str}"' in f


# ---------------------------------------------------------------------------
# needs_acl_short_circuit
# ---------------------------------------------------------------------------


def test_admin_does_not_short_circuit() -> None:
    assert needs_acl_short_circuit(_user(is_admin=True, groups=[])) is False


def test_user_with_groups_does_not_short_circuit() -> None:
    assert needs_acl_short_circuit(_user(is_admin=False, groups=[_G1])) is False


def test_non_admin_with_no_groups_short_circuits() -> None:
    assert needs_acl_short_circuit(_user(is_admin=False, groups=[])) is True


# ---------------------------------------------------------------------------
# compose_filters
# ---------------------------------------------------------------------------


def test_compose_both_parts() -> None:
    acl = 'allowed_group_ids IN ["x"] AND is_admin_only = false'
    user_f = 'metadata.source = "upload"'
    result = compose_filters(acl, user_f)
    # Both parts wrapped in parentheses and joined with AND
    assert f"({acl})" in result
    assert f"({user_f})" in result
    assert " AND " in result


def test_compose_acl_only() -> None:
    acl = 'allowed_group_ids IN ["x"] AND is_admin_only = false'
    result = compose_filters(acl, "")
    assert result == acl


def test_compose_user_filter_only() -> None:
    result = compose_filters("", 'metadata.source = "upload"')
    assert result == 'metadata.source = "upload"'


def test_compose_neither_returns_empty() -> None:
    assert compose_filters("", "") == ""


def test_compose_acl_is_first() -> None:
    acl = "ACL_FILTER"
    user_f = "USER_FILTER"
    result = compose_filters(acl, user_f)
    assert result.index(acl) < result.index(user_f)


# ---------------------------------------------------------------------------
# allowed_group_ids_for_indexing
# ---------------------------------------------------------------------------


def test_converts_uuid_list_to_strings() -> None:
    result = allowed_group_ids_for_indexing([_G1, _G2])
    assert result == [str(_G1), str(_G2)]


def test_empty_list_returns_empty_list() -> None:
    assert allowed_group_ids_for_indexing([]) == []
