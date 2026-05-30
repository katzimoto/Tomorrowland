"""Tests for LDAP group search, mapping persistence, admin routes, and auth (#582)."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from services.auth.ldap import LdapProfile
from services.auth.ldap_group_mapping_repository import LdapGroupMappingRepository
from services.auth.repository import AuthRepository
from shared.config import Settings

# ---------------------------------------------------------------------------
# LDAP group mapping repository tests
# ---------------------------------------------------------------------------


def test_create_and_list_mapping(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        # Create a target group.
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("engineering")

        repo = LdapGroupMappingRepository(connection)
        mapping = repo.create_mapping(
            ldap_dn="CN=eng,OU=Groups,DC=company,DC=local",
            ldap_external_id_attr="objectGUID",
            ldap_external_id="aabbccdd",
            ldap_display_name="Engineering",
            target_group_id=group_id,
        )

    assert mapping["ldap_dn"] == "CN=eng,OU=Groups,DC=company,DC=local"
    assert mapping["target_group_id"] == str(group_id)
    assert mapping["target_group_name"] == "engineering"
    assert mapping["ldap_external_id"] == "aabbccdd"

    # List should include it.
    with migrated_engine.begin() as connection:
        repo = LdapGroupMappingRepository(connection)
        all_mappings = repo.list_mappings()
    assert len(all_mappings) == 1
    assert all_mappings[0]["id"] == mapping["id"]


def test_delete_mapping(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("test-group")

        repo = LdapGroupMappingRepository(connection)
        mapping = repo.create_mapping(
            ldap_dn="CN=test,OU=Groups,DC=company,DC=local",
            ldap_external_id_attr="objectGUID",
            ldap_external_id="eeff0011",
            ldap_display_name="Test",
            target_group_id=group_id,
        )

        # Delete it.
        from uuid import UUID

        deleted = repo.delete_mapping(UUID(mapping["id"]))
        assert deleted is True

        # Verify gone.
        all_mappings = repo.list_mappings()
        assert len(all_mappings) == 0

        # Delete already-deleted returns False.
        deleted2 = repo.delete_mapping(UUID(mapping["id"]))
        assert deleted2 is False


def test_duplicate_dn_rejected(migrated_engine: Engine) -> None:
    import sqlalchemy as sa

    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("duplicate-test")

        repo = LdapGroupMappingRepository(connection)
        repo.create_mapping(
            ldap_dn="CN=unique,OU=Groups,DC=company,DC=local",
            ldap_external_id_attr="objectGUID",
            ldap_external_id="unique001",
            ldap_display_name="Unique",
            target_group_id=group_id,
        )

        with pytest.raises(sa.exc.IntegrityError):
            repo.create_mapping(
                ldap_dn="CN=unique,OU=Groups,DC=company,DC=local",
                ldap_external_id_attr="objectGUID",
                ldap_external_id="unique002",
                ldap_display_name="Duplicate",
                target_group_id=group_id,
            )


def test_get_mapped_tomorrowland_group_ids(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        g1 = auth_repo.ensure_group("group-a")
        g2 = auth_repo.ensure_group("group-b")

        repo = LdapGroupMappingRepository(connection)
        repo.create_mapping(
            ldap_dn="CN=groupA,DC=company,DC=local",
            ldap_external_id_attr="objectGUID",
            ldap_external_id="a1",
            ldap_display_name="Group A",
            target_group_id=g1,
        )
        repo.create_mapping(
            ldap_dn="CN=groupB,DC=company,DC=local",
            ldap_external_id_attr="objectGUID",
            ldap_external_id="b1",
            ldap_display_name="Group B",
            target_group_id=g2,
        )

        # Query with matching and non-matching DNs.
        result = repo.get_mapped_tomorrowland_group_ids(
            ["CN=groupA,DC=company,DC=local", "CN=nonexistent,DC=company,DC=local"]
        )
        assert result == [g1]

        # Empty input returns empty.
        assert repo.get_mapped_tomorrowland_group_ids([]) == []


def test_get_mapping_by_dn(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("search-test")

        repo = LdapGroupMappingRepository(connection)
        repo.create_mapping(
            ldap_dn="CN=search-me,DC=company,DC=local",
            ldap_external_id_attr="objectGUID",
            ldap_external_id="search1",
            ldap_display_name="Search Me",
            target_group_id=group_id,
        )

        found = repo.get_mapping_by_dn("CN=search-me,DC=company,DC=local")
        assert found is not None
        assert found["ldap_display_name"] == "Search Me"

        not_found = repo.get_mapping_by_dn("CN=missing,DC=company,DC=local")
        assert not_found is None


# ---------------------------------------------------------------------------
# LDAP filter escaping tests
# ---------------------------------------------------------------------------


def test_ldap_filter_escape() -> None:
    from services.auth.ldap_client import _escape_ldap_filter_value

    # Parentheses and asterisks must be escaped per RFC 4515.
    assert _escape_ldap_filter_value("test*") == "test\\2a"
    assert _escape_ldap_filter_value("(foo)") == "\\28foo\\29"
    assert _escape_ldap_filter_value("a\\b") == "a\\5cb"
    # Normal text is unchanged.
    assert _escape_ldap_filter_value("engineering") == "engineering"


def test_ldap_search_empty_query() -> None:
    from services.auth.ldap_client import LdapClient

    settings = Settings()
    client = LdapClient(settings)
    # Without a real LDAP server, search_groups should return empty when
    # given an empty query.
    assert client.search_groups("") == []
    assert client.search_groups("   ") == []


# ---------------------------------------------------------------------------
# Auth integration: unmapped LDAP groups do not grant access
# ---------------------------------------------------------------------------


def test_upsert_ldap_user_resolves_only_mapped_groups(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        # Create Tomorrowland groups.
        mapped_group_id = auth_repo.ensure_group("mapped-ldap-group")

        # Create a mapping for one LDAP group.
        repo = LdapGroupMappingRepository(connection)
        repo.create_mapping(
            ldap_dn="CN=mapped,DC=company,DC=local",
            ldap_external_id_attr="objectGUID",
            ldap_external_id="mapped-ext",
            ldap_display_name="Mapped Group",
            target_group_id=mapped_group_id,
        )

        # Upsert user with two LDAP groups (one mapped, one unmapped).
        profile = LdapProfile(
            email="ldapuser@company.local",
            display_name="LDAP User",
            group_names=[
                "CN=mapped,DC=company,DC=local",
                "CN=unmapped,DC=company,DC=local",
            ],
        )
        user = auth_repo.upsert_ldap_user(profile)

        # User should only have the mapped group.
        assert mapped_group_id in user.groups

        # Unmapped group should never appear.
        unmapped_id = auth_repo.ensure_group("unmapped-auto")
        assert unmapped_id not in user.groups


def test_upsert_ldap_user_with_no_mappings_gets_no_groups(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)

        profile = LdapProfile(
            email="nomaps@company.local",
            display_name="No Maps User",
            group_names=["CN=orphan,DC=company,DC=local"],
        )
        user = auth_repo.upsert_ldap_user(profile)

        # No mappings exist, so the user should have no groups.
        assert user.groups == []


def test_missing_target_group_rejected(migrated_engine: Engine) -> None:
    from uuid import uuid4

    with migrated_engine.begin() as connection:
        repo = LdapGroupMappingRepository(connection)

        with pytest.raises(ValueError, match="does not exist"):
            repo.create_mapping(
                ldap_dn="CN=bad-target,DC=company,DC=local",
                ldap_external_id_attr="objectGUID",
                ldap_external_id="bad1",
                ldap_display_name="Bad Target",
                target_group_id=uuid4(),  # non-existent group
            )
