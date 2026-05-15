from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    """Hash a local password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a local password against a bcrypt hash."""
    if password_hash is None:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
