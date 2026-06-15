"""Tests for CTranslate2OpusProvider (#731)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from services.translation.ctranslate2_provider import CTranslate2OpusProvider
from services.translation.provider import TranslationProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_manifest_dict(pairs: list[dict[str, str]] | None = None) -> dict[str, Any]:
    if pairs is None:
        pairs = [
            {"source": "en", "target": "he"},
            {"source": "he", "target": "en"},
        ]
    files = []
    for pair in pairs:
        src, tgt = pair["source"], pair["target"]
        dir_name = f"{src}-{tgt}"
        files.append({"path": f"models/{dir_name}/model.bin", "sha256": "", "size_bytes": 1024})
        files.append({"path": f"models/{dir_name}/config.json", "sha256": "", "size_bytes": 256})
        files.append({"path": f"models/{dir_name}/source.spm", "sha256": "", "size_bytes": 512})
        files.append({"path": f"models/{dir_name}/target.spm", "sha256": "", "size_bytes": 512})
    return {
        "bundle_version": "1.0",
        "tomorrowland_release": "0.7.0",
        "created_at": "2026-06-15T00:00:00Z",
        "provider": {
            "name": "opus_mt",
            "version": "OPUS-MT-2024",
            "model_family": "opus",
            "format": "ctranslate2",
        },
        "supported_languages": ["en", "he"],
        "language_pairs": pairs,
        "models_dir": "models",
        "expected_env": {},
        "files": files,
        "license": {
            "name": "CC-BY-4.0",
            "verification_status": "verified",
        },
    }


def _create_bundle_with_manifest(
    bundle_root: Path, manifest_dict: dict[str, Any] | None = None
) -> Path:
    """Create a bundle directory with manifest.json and model directories.

    Writes deterministic content for each file and updates the manifest
    dict's SHA-256 values to match the actual file contents so the
    BundleValidator checks pass.
    """
    if manifest_dict is None:
        manifest_dict = _make_manifest_dict()
    bundle_root.mkdir(parents=True)

    models_dir = bundle_root / manifest_dict["models_dir"]
    content_map: dict[str, bytes] = {
        "model.bin": b"dummy model data",
        "config.json": b"{}",
        "source.spm": b"dummy spm",
        "target.spm": b"dummy spm",
    }

    # Compute SHA-256 digests and update manifest
    file_index: dict[str, dict[str, Any]] = {}
    for f in manifest_dict["files"]:
        file_index[f["path"]] = f

    for pair in manifest_dict["language_pairs"]:
        pair_dir = models_dir / f"{pair['source']}-{pair['target']}"
        pair_dir.mkdir(parents=True)
        for filename, content in content_map.items():
            file_path = pair_dir / filename
            file_path.write_bytes(content)
            manifest_path = f"models/{pair['source']}-{pair['target']}/{filename}"
            if manifest_path in file_index:
                file_index[manifest_path]["sha256"] = hashlib.sha256(content).hexdigest()

    (bundle_root / "manifest.json").write_text(json.dumps(manifest_dict), encoding="utf-8")
    return bundle_root


# ---------------------------------------------------------------------------
# Mock helpers — patch ctranslate2 and sentencepiece in sys.modules for
# lazy imports inside _load_pair / _load_sentencepiece.
# ---------------------------------------------------------------------------


def _mock_ctranslate2_modules(
    mock_translator: MagicMock | None = None,
    mock_sentencepiece: MagicMock | None = None,
) -> dict[str, Any]:
    """Return a dict suitable for ``patch.dict(sys.modules, ...)``."""
    mods: dict[str, Any] = {}
    if mock_translator is None:
        mock_translator = MagicMock()
    fake_ct2 = MagicMock()
    fake_ct2.Translator.return_value = mock_translator
    mods["ctranslate2"] = fake_ct2

    if mock_sentencepiece is not None:
        fake_spm = MagicMock()
        fake_spm.SentencePieceProcessor.return_value = mock_sentencepiece
        mods["sentencepiece"] = fake_spm
    return mods


class FakeBaseline(TranslationProvider):
    """Minimal fake baseline provider for testing fallback behavior."""

    @property
    def name(self) -> str:
        return "fake_baseline"

    @property
    def version(self) -> str | None:
        return "fake-1.0"

    @property
    def model_family(self) -> str | None:
        return "fake"

    def translate(self, text: str, source_lang: str | None, target_lang: str = "en") -> str:
        return f"[baseline:{target_lang}]{text}[/baseline]"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCTranslate2OpusProviderInit:
    """Provider initialization and manifest loading."""

    def test_loads_bundle_with_manifest(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle))
            assert provider.name == "opus_mt"
            assert provider.model_family == "opus"
            assert provider.version == "OPUS-MT-2024"

    def test_missing_manifest_reports_error(self, tmp_path: Path) -> None:
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        provider = CTranslate2OpusProvider(bundle_path=str(bundle))
        health = provider.health()
        assert health["status"] == "unhealthy"
        assert not health["bundle_valid"]

    def test_invalid_manifest_reports_error(self, tmp_path: Path) -> None:
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        (bundle / "manifest.json").write_text("not json", encoding="utf-8")
        provider = CTranslate2OpusProvider(bundle_path=str(bundle))
        health = provider.health()
        assert health["status"] == "unhealthy"

    def test_missing_model_directories_reported(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        import shutil

        shutil.rmtree(bundle / "models" / "en-he")

        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle))
            health = provider.health()
            assert health["loaded_pairs"] == 1

    def test_loads_sentencepiece_tokenizers(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        mock_tr = MagicMock()
        mock_sp = MagicMock()
        mock_mods = _mock_ctranslate2_modules(mock_translator=mock_tr, mock_sentencepiece=mock_sp)
        with patch.dict(sys.modules, mock_mods):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle))
            assert len(provider._translators) == 2
            assert len(provider._tokenizers) == 2


class TestCTranslate2OpusProviderTranslate:
    """Translation and fallback behavior."""

    def test_translates_supported_pair(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        baseline = FakeBaseline()

        mock_tr = MagicMock()
        mock_result = MagicMock()
        mock_result.hypotheses = [["שָׁלוֹם"]]
        mock_tr.translate_batch.return_value = [mock_result]

        mock_sp = MagicMock()
        mock_sp.encode.return_value = ["Hello"]
        mock_sp.decode.return_value = "שָׁלוֹם"

        mock_mods = _mock_ctranslate2_modules(mock_translator=mock_tr, mock_sentencepiece=mock_sp)
        with patch.dict(sys.modules, mock_mods):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle), baseline=baseline)
            result = provider.translate("Hello", source_lang="en", target_lang="he")
            assert result == "שָׁלוֹם"

    def test_falls_back_for_unsupported_pair(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        baseline = FakeBaseline()

        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle), baseline=baseline)
            result = provider.translate("Bonjour", source_lang="fr", target_lang="en")
            assert result == "[baseline:en]Bonjour[/baseline]"

    def test_falls_back_when_source_lang_is_none(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        baseline = FakeBaseline()

        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle), baseline=baseline)
            result = provider.translate("Hello", source_lang=None, target_lang="he")
            assert result == "[baseline:he]Hello[/baseline]"

    def test_falls_back_on_ctranslate2_error(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        baseline = FakeBaseline()

        mock_tr = MagicMock()
        mock_tr.translate_batch.side_effect = RuntimeError("model crash")
        mock_sp = MagicMock()
        mock_sp.encode.return_value = ["Hello"]

        mock_mods = _mock_ctranslate2_modules(mock_translator=mock_tr, mock_sentencepiece=mock_sp)
        with patch.dict(sys.modules, mock_mods):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle), baseline=baseline)
            result = provider.translate("Hello", source_lang="en", target_lang="he")
            assert result == "[baseline:he]Hello[/baseline]"

    def test_returns_original_when_no_baseline(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")

        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle), baseline=None)
            result = provider.translate("Bonjour", source_lang="fr", target_lang="en")
            assert result == "Bonjour"


class TestCTranslate2OpusProviderCapabilities:
    """Capabilities and health reporting."""

    def test_capabilities_report_loaded_pairs(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle))
            caps = provider.capabilities
            assert caps["model_family"] == "opus"
            assert caps["supports_batch"] is True
            assert caps["supports_auto_detect"] is False
            assert caps["loaded_pair_count"] == 2
            pairs = caps["language_pairs"]
            assert {"source": "en", "target": "he"} in pairs
            assert {"source": "he", "target": "en"} in pairs

    def test_health_healthy_with_loaded_pairs(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle))
            health = provider.health()
            assert health["status"] == "healthy"
            assert health["bundle_valid"] is True
            assert health["loaded_pairs"] == 2
            assert health["baseline_available"] is False

    def test_health_reports_baseline_available(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        baseline = FakeBaseline()
        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle), baseline=baseline)
            health = provider.health()
            assert health["baseline_available"] is True

    def test_default_identity_when_no_manifest(self, tmp_path: Path) -> None:
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        provider = CTranslate2OpusProvider(bundle_path=str(bundle))
        assert provider.name == "opus_mt_ctranslate2"
        assert provider.model_family == "opus"
        assert provider.version is None


class TestCTranslate2OpusProviderClose:
    """Resource cleanup."""

    def test_close_clears_translators_and_closes_baseline(self, tmp_path: Path) -> None:
        bundle = _create_bundle_with_manifest(tmp_path / "bundle")
        baseline = MagicMock(spec=TranslationProvider)
        mock_tr = MagicMock()
        with patch.dict(sys.modules, _mock_ctranslate2_modules(mock_translator=mock_tr)):
            provider = CTranslate2OpusProvider(bundle_path=str(bundle), baseline=baseline)
            assert len(provider._translators) == 2
            provider.close()
            assert len(provider._translators) == 0
            assert len(provider._tokenizers) == 0
            baseline.close.assert_called_once()
