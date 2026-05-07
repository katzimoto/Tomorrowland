from __future__ import annotations

from fastapi import HTTPException

from services.auth.jwt import JwtService
from services.auth.ldap import LdapAuthenticator
from services.auth.models import LoginResponse, UserResponse
from services.auth.passwords import verify_password
from services.auth.repository import AuthRepository


class AuthService:
    """Authenticate users through LDAP and/or local credentials."""

    def __init__(
        self,
        repository: AuthRepository,
        jwt_service: JwtService,
        auth_provider: str,
        ldap_authenticator: LdapAuthenticator | None = None,
    ) -> None:
        self._repository = repository
        self._jwt_service = jwt_service
        self._auth_provider = auth_provider
        self._ldap_authenticator = ldap_authenticator

    def authenticate(self, email: str, password: str) -> LoginResponse:
        """Authenticate credentials and return a bearer token."""
        user = None
        if self._auth_provider in {"ldap", "both"} and self._ldap_authenticator is not None:
            profile = self._ldap_authenticator.authenticate(email, password)
            if profile is not None:
                user = self._repository.upsert_ldap_user(profile)

        if user is None and self._auth_provider in {"local", "both"}:
            password_hash = self._repository.get_password_hash(email)
            if verify_password(password, password_hash):
                user = self._repository.get_user_by_email(email)

        if user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        self._repository.touch_last_login(user.id)
        return LoginResponse(
            access_token=self._jwt_service.encode(user),
            user=UserResponse.from_identity(user),
        )
