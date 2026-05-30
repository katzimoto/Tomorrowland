"""Encrypted credential store for model provider API keys.

Uses Fernet symmetric encryption. The encryption key is derived from
``Settings.credential_store_key``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import sqlalchemy as sa
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

MASK_PREFIX = "tl-cred:"
MASK_SUFFIX_LEN = 4


def mask_credential(value: str | None) -> str | None:
    """Return a masked version of a credential value for safe logging/display.

    Shows only the last *MASK_SUFFIX_LEN* characters; replaces the rest
    with ``"••••••••"``.
    """
    if value is None:
        return None
    if len(value) <= MASK_SUFFIX_LEN + 2:
        return "••••••••"
    return "••••••••" + value[-MASK_SUFFIX_LEN:]


def _derive_fernet_key(master_secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length secret."""

    return Fernet.generate_key() if master_secret == "dev-only" else _make_key(master_secret)


def _make_key(secret: str) -> bytes:
    import hashlib

    raw = hashlib.sha256(secret.encode()).digest()
    from base64 import urlsafe_b64encode

    return urlsafe_b64encode(raw)


class CredentialStore:
    """Encrypted credential storage backed by the ``provider_credentials`` table.

    Each credential is stored as a Fernet-encrypted blob in a dedicated table,
    keyed by a human-readable *key_name* (e.g. ``"my-ollama-key"``).

    The *api_key_ref* field on ``model_providers`` stores this *key_name* so the
    two are decoupled — the provider row never contains a plaintext secret.
    """

    def __init__(self, connection: Connection, fernet_key: str) -> None:
        self._connection = connection
        self._fernet = Fernet(_derive_fernet_key(fernet_key))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_credential(self, key_name: str, plaintext: str) -> str:
        """Encrypt and store a credential. Upserts on key_name."""
        encrypted = self._fernet.encrypt(plaintext.encode())
        now = datetime.now(UTC)
        self._connection.execute(
            sa.text("""
                INSERT INTO provider_credentials (key_name, encrypted_value, created_at, updated_at)
                VALUES (:key_name, :encrypted_value, :created_at, :updated_at)
                ON CONFLICT (key_name) DO UPDATE SET
                    encrypted_value = EXCLUDED.encrypted_value,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "key_name": key_name,
                "encrypted_value": encrypted.decode(),
                "created_at": now,
                "updated_at": now,
            },
        )
        return key_name

    def get_credential(self, key_name: str) -> str | None:
        """Decrypt and return a credential, or None if not found."""
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT encrypted_value FROM provider_credentials WHERE key_name = :key_name"
                ),
                {"key_name": key_name},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        try:
            return self._fernet.decrypt(row["encrypted_value"].encode()).decode()
        except InvalidToken:
            logger.error("Failed to decrypt credential key_name=%s", key_name)
            return None

    def delete_credential(self, key_name: str) -> bool:
        """Delete a stored credential. Returns True if one was deleted."""
        result = self._connection.execute(
            sa.text("DELETE FROM provider_credentials WHERE key_name = :key_name"),
            {"key_name": key_name},
        )
        return result.rowcount > 0

    def has_credential(self, key_name: str) -> bool:
        """Return True if a credential exists for *key_name*."""
        row = self._connection.execute(
            sa.text("SELECT 1 FROM provider_credentials WHERE key_name = :key_name"),
            {"key_name": key_name},
        ).first()
        return row is not None

    def list_key_names(self) -> list[str]:
        """Return all credential key names."""
        rows = self._connection.execute(
            sa.text("SELECT key_name FROM provider_credentials ORDER BY key_name")
        ).scalars()
        return list(rows)
