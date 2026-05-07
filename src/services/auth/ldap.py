from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class LdapProfile(BaseModel):
    """Normalized LDAP profile returned by an LDAP adapter."""

    email: str
    display_name: str | None = None
    group_names: list[str] = Field(default_factory=list)


class LdapAuthenticator(Protocol):
    """Boundary for real LDAP integration added outside the auth core."""

    def authenticate(self, email: str, password: str) -> LdapProfile | None:
        """Return a profile when LDAP credentials are valid."""
        ...
