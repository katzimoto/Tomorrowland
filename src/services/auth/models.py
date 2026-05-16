from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AuthSource = Literal["local", "ldap"]


class UserIdentity(BaseModel):
    """Authenticated user with resolved group memberships."""

    id: UUID
    email: str
    display_name: str | None = None
    auth_source: AuthSource
    is_admin: bool
    groups: list[UUID] = Field(default_factory=list)


class TokenPayload(BaseModel):
    """JWT payload used by backend permission checks."""

    sub: UUID
    email: str
    display_name: str | None = None
    is_admin: bool
    groups: list[UUID] = Field(default_factory=list)
    auth_source: AuthSource
    exp: int


class LoginRequest(BaseModel):
    """Login request body."""

    email: str
    password: str


class SignUpRequest(BaseModel):
    """Sign-up request body."""

    email: str
    password: str
    display_name: str | None = None


class LoginResponse(BaseModel):
    """Login response body."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


class UserResponse(BaseModel):
    """Public authenticated user shape."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None = None
    is_admin: bool
    groups: list[UUID] = Field(default_factory=list)
    auth_source: AuthSource

    @classmethod
    def from_identity(cls, user: UserIdentity) -> UserResponse:
        """Create a response from a repository identity."""
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
            groups=user.groups,
            auth_source=user.auth_source,
        )

    @classmethod
    def from_token(cls, token: TokenPayload) -> UserResponse:
        """Create a response from a verified token payload."""
        return cls(
            id=token.sub,
            email=token.email,
            display_name=token.display_name,
            is_admin=token.is_admin,
            groups=token.groups,
            auth_source=token.auth_source,
        )
