"""Tests for translation model bundle manifest parsing and validation (#730)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from services.translation.model_bundle import (
    BundleValidator,
    TranslationModelManifest,
    load_manifest_from_path,
    parse_manifest,
)

# ---------------------------------------------------------------------------
# Fixtures — minimal valid manifest
# ---------------------------------------------------------------------------


def _minimal_manifest_dict() -> dict[str, Any]:
    return {
        "bundle_version": "1.0",
        "tomorrowland_release": "0.7.0",
        "created_at": "2026-06-15T00:00:00Z",
        "provider": {
            "name": "argos",
            "version": "libretranslate-1.6.3",
            "model_family": "argos",
            "format": "argos_package",
        },
        "supported_languages": ["ar", "en", "fr"],
        "language_pairs": [
            {"source": "ar", "target": "en"},
            {"source": "en", "target": "ar"},
            {"source": "en", "target": "fr"},
            {"source": "fr", "target": "en"},
        ],
        "models_dir": "models",
        "expected_env": {
            "ARGOS_CHUNK_TYPE": "MINISBD",
            "LT_LOAD_ONLY": "ar,en,fr",
        },
        "files": [
            {"path": "models/ar-en.argosmodel", "sha256": "a" * 64, "size_bytes": 1234},
            {"path": "models/en-ar.argosmodel", "sha256": "b" * 64},
            {"path": "models/en-fr.argosmodel", "sha256": "c" * 64, "size_bytes": 5678},
            {"path": "models/fr-en.argosmodel", "sha256": "d" * 64, "size_bytes": 9012},
        ],
        "license": {
            "name": "CC-BY-SA-4.0",
            "source_url": "https://example.com/license",
            "attribution": "OPUS Project",
            "verification_status": "verified",
        },
    }


@pytest.fixture
def minimal_dict() -> dict[str, Any]:
    return _minimal_manifest_dict()


@pytest.fixture
def minimal_manifest(minimal_dict: dict[str, Any]) -> TranslationModelManifest:
    return parse_manifest(minimal_dict)


# ---------------------------------------------------------------------------
# Manifest parsing tests
# ---------------------------------------------------------------------------


class TestParseManifestSuccess:
    """Happy-path parsing of valid manifests."""

    def test_full_manifest(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.bundle_version == "1.0"
        assert manifest.tomorrowland_release == "0.7.0"
        assert manifest.created_at == "2026-06-15T00:00:00Z"

    def test_provider_info(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.provider.name == "argos"
        assert manifest.provider.model_family == "argos"
        assert manifest.provider.format == "argos_package"
        assert manifest.provider.version == "libretranslate-1.6.3"

    def test_provider_version_nullable(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["provider"]["version"] = None
        manifest = parse_manifest(minimal_dict)
        assert manifest.provider.version is None

    def test_provider_version_absent(self, minimal_dict: dict[str, Any]) -> None:
        del minimal_dict["provider"]["version"]
        manifest = parse_manifest(minimal_dict)
        assert manifest.provider.version is None

    def test_supported_languages(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.supported_languages == ["ar", "en", "fr"]

    def test_language_pairs(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert len(manifest.language_pairs) == 4
        assert manifest.language_pairs[0].source == "ar"
        assert manifest.language_pairs[0].target == "en"

    def test_language_pair_set(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert ("ar", "en") in manifest.language_pair_set
        assert ("en", "fr") in manifest.language_pair_set
        assert ("xx", "yy") not in manifest.language_pair_set

    def test_supports_pair(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.supports_pair("ar", "en")
        assert not manifest.supports_pair("en", "zh")

    def test_models_dir(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.models_dir == "models"

    def test_expected_env(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.expected_env["ARGOS_CHUNK_TYPE"] == "MINISBD"
        assert manifest.expected_env["LT_LOAD_ONLY"] == "ar,en,fr"

    def test_files(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert len(manifest.files) == 4
        assert manifest.files[0].path == "models/ar-en.argosmodel"
        assert manifest.files[0].sha256 == "a" * 64
        assert manifest.files[0].size_bytes == 1234
        # size_bytes is optional
        assert manifest.files[1].size_bytes is None

    def test_file_paths(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert "models/ar-en.argosmodel" in manifest.file_paths

    def test_checksum_for(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.checksum_for("models/ar-en.argosmodel") == "a" * 64
        assert manifest.checksum_for("nonexistent") is None

    def test_license(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        assert manifest.license is not None
        assert manifest.license.name == "CC-BY-SA-4.0"
        assert manifest.license.source_url == "https://example.com/license"
        assert manifest.license.attribution == "OPUS Project"
        assert manifest.license.verification_status == "verified"

    def test_license_optional(self, minimal_dict: dict[str, Any]) -> None:
        del minimal_dict["license"]
        manifest = parse_manifest(minimal_dict)
        assert manifest.license is None

    def test_to_dict_roundtrip(self, minimal_dict: dict[str, Any]) -> None:
        manifest = parse_manifest(minimal_dict)
        # Re-serialize and re-parse — should be structurally equivalent
        re_parsed = parse_manifest(manifest.to_dict())
        assert re_parsed.bundle_version == manifest.bundle_version
        assert re_parsed.provider.name == manifest.provider.name
        assert re_parsed.provider.version == manifest.provider.version
        assert len(re_parsed.files) == len(manifest.files)
        assert re_parsed.license is not None
        assert re_parsed.license.name == "CC-BY-SA-4.0"


class TestParseManifestErrors:
    """Structural validation of invalid manifests."""

    def test_missing_required_top_level_key(self, minimal_dict: dict[str, Any]) -> None:
        del minimal_dict["files"]
        with pytest.raises(ValueError, match="missing required key: 'files'"):
            parse_manifest(minimal_dict)

    def test_provider_not_object(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["provider"] = "argos"
        with pytest.raises(ValueError, match="'provider' must be an object"):
            parse_manifest(minimal_dict)

    def test_provider_missing_name(self, minimal_dict: dict[str, Any]) -> None:
        del minimal_dict["provider"]["name"]
        with pytest.raises(ValueError, match="missing required key: 'name'"):
            parse_manifest(minimal_dict)

    def test_provider_name_not_string(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["provider"]["name"] = 123
        with pytest.raises(ValueError, match="'name' must be a string"):
            parse_manifest(minimal_dict)

    def test_supported_languages_not_array(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["supported_languages"] = "en,fr"
        with pytest.raises(ValueError, match="must be a non-empty array"):
            parse_manifest(minimal_dict)

    def test_supported_languages_empty(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["supported_languages"] = []
        with pytest.raises(ValueError, match="must be a non-empty array"):
            parse_manifest(minimal_dict)

    def test_language_pairs_not_array(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["language_pairs"] = {}
        with pytest.raises(ValueError, match="must be a non-empty array"):
            parse_manifest(minimal_dict)

    def test_language_pair_missing_target(self, minimal_dict: dict[str, Any]) -> None:
        del minimal_dict["language_pairs"][0]["target"]
        with pytest.raises(ValueError, match="missing required key: 'target'"):
            parse_manifest(minimal_dict)

    def test_files_not_array(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["files"] = "nope"
        with pytest.raises(ValueError, match="must be a non-empty array"):
            parse_manifest(minimal_dict)

    def test_files_empty(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["files"] = []
        with pytest.raises(ValueError, match="must be a non-empty array"):
            parse_manifest(minimal_dict)

    def test_file_missing_sha256(self, minimal_dict: dict[str, Any]) -> None:
        del minimal_dict["files"][0]["sha256"]
        with pytest.raises(ValueError, match="missing required key: 'sha256'"):
            parse_manifest(minimal_dict)

    def test_file_path_not_string(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["files"][0]["path"] = 42
        with pytest.raises(ValueError, match="'path' must be a string"):
            parse_manifest(minimal_dict)

    def test_size_bytes_not_int(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["files"][0]["size_bytes"] = "large"
        with pytest.raises(ValueError, match="size_bytes must be an integer"):
            parse_manifest(minimal_dict)

    def test_expected_env_not_object(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["expected_env"] = []
        with pytest.raises(ValueError, match="'expected_env' must be an object"):
            parse_manifest(minimal_dict)

    def test_provider_version_not_string(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["provider"]["version"] = 123
        with pytest.raises(ValueError, match="'provider.version' must be a string or null"):
            parse_manifest(minimal_dict)

    def test_license_not_object(self, minimal_dict: dict[str, Any]) -> None:
        minimal_dict["license"] = "MIT"
        with pytest.raises(ValueError, match="'license' must be an object"):
            parse_manifest(minimal_dict)


# ---------------------------------------------------------------------------
# load_manifest_from_path tests
# ---------------------------------------------------------------------------


class TestLoadManifestFromPath:
    def test_loads_valid_manifest(self, tmp_path: Path, minimal_dict: dict[str, Any]) -> None:
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(minimal_dict), encoding="utf-8")
        manifest = load_manifest_from_path(path)
        assert manifest.provider.name == "argos"

    def test_rejects_non_object_root(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="must contain a JSON object"):
            load_manifest_from_path(path)

    def test_rejects_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "manifest.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_manifest_from_path(path)


# ---------------------------------------------------------------------------
# BundleValidator tests
# ---------------------------------------------------------------------------


class TestBundleValidator:
    def test_all_files_present_and_valid(
        self, tmp_path: Path, minimal_dict: dict[str, Any]
    ) -> None:
        """Happy path — every file exists and checksums match."""
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)

        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        report = validator.validate()
        assert report.valid
        assert report.missing_files == []
        assert report.checksum_mismatches == []

    def test_missing_file(self, tmp_path: Path, minimal_dict: dict[str, Any]) -> None:
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)
        # Delete one file
        (bundle_root / "models/ar-en.argosmodel").unlink()

        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        report = validator.validate()
        assert not report.valid
        assert "models/ar-en.argosmodel" in report.missing_files

    def test_checksum_mismatch(self, tmp_path: Path, minimal_dict: dict[str, Any]) -> None:
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)
        # Corrupt a file
        (bundle_root / "models/fr-en.argosmodel").write_text("corrupted", encoding="utf-8")

        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        report = validator.validate()
        assert not report.valid
        assert "models/fr-en.argosmodel" in report.checksum_mismatches

    def test_extra_unlisted_files_reported_when_strict(
        self, tmp_path: Path, minimal_dict: dict[str, Any]
    ) -> None:
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)
        # Add an unlisted file
        extra = bundle_root / "models" / "extra.model"
        extra.write_text("bonus", encoding="utf-8")

        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        report = validator.validate(strict_extra_files=True)
        assert report.valid  # extra files don't invalidate
        assert len(report.extra_unlisted_files) == 1
        assert "models/extra.model" in report.extra_unlisted_files

    def test_extra_files_ignored_by_default(
        self, tmp_path: Path, minimal_dict: dict[str, Any]
    ) -> None:
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)
        extra = bundle_root / "models" / "extra.model"
        extra.write_text("bonus", encoding="utf-8")

        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        report = validator.validate()
        assert report.valid
        assert report.extra_unlisted_files == []

    def test_missing_models_dir(self, tmp_path: Path, minimal_dict: dict[str, Any]) -> None:
        bundle_root = tmp_path / "bundle"
        bundle_root.mkdir()
        # Don't create models/ — all files should be reported missing
        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        report = validator.validate()
        assert not report.valid
        assert len(report.missing_files) == len(manifest.files)

    def test_issues_property(self, tmp_path: Path, minimal_dict: dict[str, Any]) -> None:
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)
        (bundle_root / "models/ar-en.argosmodel").unlink()

        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        report = validator.validate()
        assert any("missing: models/ar-en.argosmodel" in issue for issue in report.issues)

    def test_health_healthy(self, tmp_path: Path, minimal_dict: dict[str, Any]) -> None:
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)
        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        health = validator.health()
        assert health["status"] == "healthy"
        assert health["bundle_valid"] is True
        assert health["files_present"] == health["files_expected"]

    def test_health_unhealthy(self, tmp_path: Path, minimal_dict: dict[str, Any]) -> None:
        bundle_root = tmp_path / "bundle"
        _create_bundle_with_files(bundle_root, minimal_dict)
        (bundle_root / "models/ar-en.argosmodel").unlink()
        manifest = parse_manifest(minimal_dict)
        validator = BundleValidator(manifest, bundle_root)
        health = validator.health()
        assert health["status"] == "unhealthy"
        assert health["bundle_valid"] is False
        assert health["files_present"] < health["files_expected"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_bundle_with_files(bundle_root: Path, manifest_dict: dict[str, Any]) -> None:
    """Create a bundle directory on disk with files matching *manifest_dict*.

    Writes deterministic content for each file based on its path, then
    updates the manifest dict's SHA-256 values to match the actual file
    contents so the BundleValidator checks pass.
    """
    models_dir = bundle_root / manifest_dict["models_dir"]
    models_dir.mkdir(parents=True)
    for f in manifest_dict["files"]:
        file_path = bundle_root / f["path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        content = f["path"].encode()
        file_path.write_bytes(content)
        # Update the manifest dict with the actual SHA-256 of the content
        f["sha256"] = hashlib.sha256(content).hexdigest()
