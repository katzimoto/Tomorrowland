from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import Engine

from services.auth.jwt import JwtService
from services.auth.ldap import LdapProfile
from services.auth.passwords import hash_password, verify_password
from services.auth.repository import AuthRepository
from services.auth.service import AuthService


class FakeLdap:
    def authenticate(self, email: str, password: str) -> LdapProfile | None:
        if password != "ldap-secret":
            return None
        return LdapProfile(email=email, display_name="LDAP User", group_names=["ldap-users"])


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("secret")

    assert verify_password("secret", password_hash)
    assert not verify_password("wrong", password_hash)
    assert not verify_password("secret", None)


def test_local_auth_issues_jwt_with_group_membership(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        user = repository.create_local_user(
            email="local@example.com",
            password_hash=hash_password("secret"),
            group_names=["analysts"],
        )
        service = AuthService(repository, JwtService("x" * 32), "local")

        response = service.authenticate("local@example.com", "secret")
        payload = JwtService("x" * 32).decode(response.access_token)

    assert payload.sub == user.id
    assert payload.groups == user.groups
    assert response.user.email == "local@example.com"


def test_ldap_auth_upserts_user_and_falls_back_to_local(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        repository.create_local_user(
            email="fallback@example.com",
            password_hash=hash_password("local-secret"),
            group_names=["local-users"],
        )
        service = AuthService(repository, JwtService("x" * 32), "both", FakeLdap())

        ldap_response = service.authenticate("ldap@example.com", "ldap-secret")
        local_response = service.authenticate("fallback@example.com", "local-secret")

    assert ldap_response.user.auth_source == "ldap"
    assert ldap_response.user.groups
    assert local_response.user.auth_source == "local"


def test_auth_service_rejects_invalid_credentials(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        service = AuthService(
            AuthRepository(connection),
            JwtService("x" * 32),
            "both",
            FakeLdap(),
        )

        with pytest.raises(HTTPException) as exc_info:
            service.authenticate("unknown@example.com", "bad")

    assert exc_info.value.status_code == 401
