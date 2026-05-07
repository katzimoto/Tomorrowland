from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import HTTPException

from services.auth.models import TokenPayload, UserIdentity


class JwtService:
    """Create and verify signed access tokens."""

    def __init__(self, secret: str, ttl: timedelta = timedelta(hours=8)) -> None:
        self._secret = secret
        self._ttl = ttl

    def encode(self, user: UserIdentity) -> str:
        """Encode a user identity as an HS256 JWT."""
        expires_at = datetime.now(UTC) + self._ttl
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
            "groups": [str(group_id) for group_id in user.groups],
            "auth_source": user.auth_source,
            "exp": expires_at,
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")

    def decode(self, token: str) -> TokenPayload:
        """Decode a JWT into a token payload."""
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc

        return TokenPayload(
            sub=UUID(payload["sub"]),
            email=payload["email"],
            display_name=payload.get("display_name"),
            is_admin=payload["is_admin"],
            groups=[UUID(group_id) for group_id in payload["groups"]],
            auth_source=payload["auth_source"],
            exp=payload["exp"],
        )
