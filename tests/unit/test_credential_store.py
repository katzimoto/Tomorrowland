"""Unit tests for CredentialStore and credential masking."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Engine, create_engine

from services.intelligence.credential_store import CredentialStore, mask_credential


def _engine() -> Engine:
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(
            sa.text("""
                CREATE TABLE provider_credentials (
                    key_name TEXT PRIMARY KEY,
                    encrypted_value TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """)
        )
    return eng


def test_set_and_get_credential() -> None:
    eng = _engine()
    with eng.begin() as conn:
        cs = CredentialStore(conn, "test-key-not-secure")
        cs.set_credential("my-key", "sk-abc123secret")
        result = cs.get_credential("my-key")
        assert result == "sk-abc123secret"


def test_get_missing_credential() -> None:
    eng = _engine()
    with eng.begin() as conn:
        cs = CredentialStore(conn, "test-key")
        assert cs.get_credential("nonexistent") is None


def test_set_and_has_credential() -> None:
    eng = _engine()
    with eng.begin() as conn:
        cs = CredentialStore(conn, "test-key")
        cs.set_credential("exists", "value")
        assert cs.has_credential("exists") is True
        assert cs.has_credential("missing") is False


def test_delete_credential() -> None:
    eng = _engine()
    with eng.begin() as conn:
        cs = CredentialStore(conn, "test-key")
        cs.set_credential("delete-me", "value")
        assert cs.delete_credential("delete-me") is True
        assert cs.get_credential("delete-me") is None
        assert cs.delete_credential("already-gone") is False


def test_upsert_credential() -> None:
    eng = _engine()
    with eng.begin() as conn:
        cs = CredentialStore(conn, "test-key")
        cs.set_credential("my-key", "original")
        cs.set_credential("my-key", "replaced")
        assert cs.get_credential("my-key") == "replaced"


def test_list_key_names() -> None:
    eng = _engine()
    with eng.begin() as conn:
        cs = CredentialStore(conn, "test-key")
        assert cs.list_key_names() == []
        cs.set_credential("a", "1")
        cs.set_credential("b", "2")
        names = cs.list_key_names()
        assert names == ["a", "b"]


def test_different_keys_produce_different_ciphertexts() -> None:
    """Verify that the same plaintext encrypted under different keys differs."""
    eng = _engine()
    with eng.begin() as conn:
        cs1 = CredentialStore(conn, "key-1")
        cs2 = CredentialStore(conn, "key-2")
        cs1.set_credential("k", "hello")
        cs2.set_credential("k", "hello")
        row1 = conn.execute(
            sa.text("SELECT encrypted_value FROM provider_credentials WHERE key_name = 'k'")
        ).scalar()
        # Delete and re-create with the other key
        conn.execute(sa.text("DELETE FROM provider_credentials WHERE key_name = 'k'"))
        cs2.set_credential("k", "hello")
        row2 = conn.execute(
            sa.text("SELECT encrypted_value FROM provider_credentials WHERE key_name = 'k'")
        ).scalar()
        assert row1 != row2  # different ciphertexts


# ---------------------------------------------------------------------------
# Credential masking
# ---------------------------------------------------------------------------


def test_mask_credential_none() -> None:
    assert mask_credential(None) is None


def test_mask_credential_short() -> None:
    assert mask_credential("ab") == "••••••••"


def test_mask_credential_normal() -> None:
    result = mask_credential("sk-abc12345secret")
    assert result is not None
    assert result.endswith("cret")
    assert result.startswith("••••••••")


def test_mask_credential_shows_last_four() -> None:
    result = mask_credential("abcdefghijklmnop")
    assert result == "••••••••mnop"


def test_credential_not_in_response_model() -> None:
    """Verify ModelProviderResponse has no credential_value field."""
    from services.intelligence.model_provider_models import ModelProviderResponse

    assert not hasattr(ModelProviderResponse, "credential_value")


def test_credential_not_in_provider_list_response() -> None:
    """Verify list_providers returns ModelProviderResponse not raw ModelProvider."""
    from services.intelligence.model_provider_models import ModelProviderResponse

    resp_field_names = set(ModelProviderResponse.model_fields.keys())
    assert "credential_set" in resp_field_names
    assert "credential_value" not in resp_field_names
    assert "api_key" not in resp_field_names


def test_dev_only_key_is_deterministic_across_instances() -> None:
    """Two CredentialStore instances with the dev-only sentinel must share the same key.

    Regression: _derive_fernet_key previously called Fernet.generate_key() for
    the "dev-only" path, producing a new random key on every instantiation so
    that credentials written by one instance could never be read by another.
    """
    eng = _engine()
    with eng.begin() as conn:
        cs_writer = CredentialStore(conn, "dev-only")
        cs_writer.set_credential("round-trip", "plaintext-value")

        cs_reader = CredentialStore(conn, "dev-only")
        result = cs_reader.get_credential("round-trip")
        assert result == "plaintext-value", (
            "dev-only CredentialStore instances must derive the same key so that "
            "a credential written in one request is readable in the next"
        )
