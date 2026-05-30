"""Unit tests for SSRF / URL validation."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.intelligence.ssrf_validation import (
    validate_locality,
    validate_provider_url,
)


class TestValidateLocality:
    def test_valid_values(self) -> None:
        assert validate_locality("local") == "local"
        assert validate_locality("self_hosted") == "self_hosted"
        assert validate_locality("external") == "external"
        assert validate_locality("  LOCAL  ") == "local"
        assert validate_locality("SELF_HOSTED") == "self_hosted"

    def test_invalid_values(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_locality("invalid")
        assert exc.value.status_code == 422

        with pytest.raises(HTTPException) as exc:
            validate_locality("")
        assert exc.value.status_code == 422


class TestValidateProviderURL:
    def test_none_or_empty_allowed(self) -> None:
        assert validate_provider_url(None, "local") is None
        assert validate_provider_url(None, "self_hosted") is None
        assert validate_provider_url(None, "external") is None
        assert validate_provider_url("", "local") is None

    def test_missing_scheme_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_provider_url("ollama:11434", "local")
        assert exc.value.status_code == 422

    def test_bad_scheme_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_provider_url("ftp://ollama:11434", "local")
        assert exc.value.status_code == 422
        assert "ftp" in str(exc.value.detail)

    def test_valid_url_local_allowed(self) -> None:
        result = validate_provider_url("http://ollama:11434", "local")
        assert result == "http://ollama:11434"

    def test_valid_url_self_hosted_allowed(self) -> None:
        result = validate_provider_url("https://my-gpu.internal:8080", "self_hosted")
        assert result == "https://my-gpu.internal:8080"

    def test_valid_url_external_allowed(self) -> None:
        result = validate_provider_url("https://api.openai.com/v1", "external")
        assert result == "https://api.openai.com/v1"

    def test_external_private_ip_blocked(self) -> None:
        """External providers must not use private IPs."""
        with pytest.raises(HTTPException) as exc:
            validate_provider_url("http://192.168.1.1:11434", "external")
        assert exc.value.status_code == 422

    def test_external_loopback_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_provider_url("http://127.0.0.1:11434", "external")
        assert exc.value.status_code == 422

    def test_local_private_ip_allowed(self) -> None:
        """Local providers may target private IPs."""
        result = validate_provider_url("http://127.0.0.1:11434", "local")
        assert result == "http://127.0.0.1:11434"

    def test_self_hosted_private_ip_allowed(self) -> None:
        result = validate_provider_url("http://10.0.0.5:8080", "self_hosted")
        assert result == "http://10.0.0.5:8080"

    def test_external_rfc1918_10_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_provider_url("http://10.0.0.1:8000", "external")
        assert exc.value.status_code == 422

    def test_external_rfc1918_172_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_provider_url("http://172.16.0.1:8000", "external")
        assert exc.value.status_code == 422

    def test_external_link_local_blocked(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_provider_url("http://169.254.1.1:8000", "external")
        assert exc.value.status_code == 422

    def test_external_hostname_not_blocked(self) -> None:
        """Public hostnames should be allowed for external providers."""
        result = validate_provider_url("https://api.openai.com/v1/models", "external")
        assert result == "https://api.openai.com/v1/models"
