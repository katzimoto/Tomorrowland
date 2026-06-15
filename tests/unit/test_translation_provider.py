"""Unit tests for TranslationProvider interface and LibreTranslateArgosProvider (#729)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.translation.libretranslate_provider import LibreTranslateArgosProvider
from services.translation.provider import TranslationProvider


class TestTranslationProviderABC:
    """Verify the abstract interface can be correctly implemented."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        with pytest.raises(TypeError):
            TranslationProvider()  # type: ignore[abstract]

    def test_can_instantiate_concrete_implementation(self) -> None:
        class _FakeProvider(TranslationProvider):
            @property
            def name(self) -> str:
                return "fake"

            @property
            def version(self) -> str | None:
                return None

            @property
            def model_family(self) -> str | None:
                return None

            def translate(self, text: str, source_lang: str | None, target_lang: str = "en") -> str:
                return text

        provider = _FakeProvider()
        assert provider.name == "fake"
        assert provider.version is None
        assert provider.translate("hello", None) == "hello"

    def test_default_capabilities_is_empty_dict(self) -> None:
        class _MinimalProvider(TranslationProvider):
            name = "minimal"
            version = None
            model_family = None

            def translate(self, text: str, source_lang: str | None, target_lang: str = "en") -> str:
                return text

        provider = _MinimalProvider()
        assert provider.capabilities == {}

    def test_default_health_is_unknown(self) -> None:
        class _MinimalProvider(TranslationProvider):
            name = "minimal"
            version = None
            model_family = None

            def translate(self, text: str, source_lang: str | None, target_lang: str = "en") -> str:
                return text

        provider = _MinimalProvider()
        assert provider.health() == {"status": "unknown", "provider": "minimal"}

    def test_close_is_noop_by_default(self) -> None:
        class _MinimalProvider(TranslationProvider):
            name = "minimal"
            version = None
            model_family = None

            def translate(self, text: str, source_lang: str | None, target_lang: str = "en") -> str:
                return text

        provider = _MinimalProvider()
        provider.close()  # must not raise


class TestLibreTranslateArgosProvider:
    """Test the concrete provider adapter."""

    def test_provider_identity(self) -> None:
        provider = LibreTranslateArgosProvider(base_url="http://localhost:5000")
        assert provider.name == "libretranslate_argos"
        assert provider.model_family == "argos"

    def test_provider_capabilities(self) -> None:
        provider = LibreTranslateArgosProvider()
        caps = provider.capabilities
        assert caps["supports_auto_detect"] is True
        assert caps["supports_batch"] is False
        assert "max_chars_per_request" in caps

    def test_translate_delegates_to_client(self) -> None:
        provider = LibreTranslateArgosProvider(base_url="http://localhost:5000")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"translatedText": "Bonjour le monde"}

        with patch("httpx.Client.post", return_value=mock_response):
            result = provider.translate("Hello world", source_lang="en", target_lang="fr")

        assert result == "Bonjour le monde"

    def test_translate_timeout_fallback(self) -> None:
        provider = LibreTranslateArgosProvider(base_url="http://localhost:5000")

        with patch("httpx.Client.post", side_effect=httpx.TimeoutException("timeout")):
            result = provider.translate("Hello world", source_lang="en", target_lang="fr")

        assert result == "Hello world"

    def test_translate_empty_text(self) -> None:
        provider = LibreTranslateArgosProvider()
        result = provider.translate("", source_lang="en")
        assert result == ""

    def test_health_healthy(self) -> None:
        provider = LibreTranslateArgosProvider(base_url="http://localhost:5000")
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.Client.get", return_value=mock_response):
            health = provider.health()

        assert health["status"] == "healthy"
        assert health["provider"] == "libretranslate_argos"
        assert "latency_ms" in health

    def test_health_unhealthy(self) -> None:
        provider = LibreTranslateArgosProvider(base_url="http://localhost:5000")

        with patch("httpx.Client.get", side_effect=httpx.ConnectError("refused")):
            health = provider.health()

        assert health["status"] == "unhealthy"

    def test_close_delegates_to_client(self) -> None:
        provider = LibreTranslateArgosProvider()
        with patch.object(provider._client, "close") as mock_close:
            provider.close()
            mock_close.assert_called_once()

    def test_version_from_spec_endpoint(self) -> None:
        """Provider fetches version lazily from /spec."""
        provider = LibreTranslateArgosProvider(base_url="http://localhost:5000")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"info": {"version": "1.6.0"}}

        with patch("httpx.Client.get", return_value=mock_response):
            assert provider.version == "libretranslate-1.6.0"

    def test_name_and_model_family_even_when_spec_fails(self) -> None:
        """Name and model_family have hardcoded defaults, even when spec is unreachable."""
        provider = LibreTranslateArgosProvider(base_url="http://localhost:5000")

        with patch("httpx.Client.get", side_effect=httpx.ConnectError("refused")):
            assert provider.name == "libretranslate_argos"
            assert provider.model_family == "argos"

    def test_isinstance_of_translation_provider(self) -> None:
        provider = LibreTranslateArgosProvider()
        assert isinstance(provider, TranslationProvider)
