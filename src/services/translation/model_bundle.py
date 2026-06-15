"""Translation model bundle — manifest, validation, and offline loader (#730).

Defines the :class:`TranslationModelManifest` dataclass, a
:class:`BundleValidator` that checks file integrity against the manifest,
and helper functions to load and verify bundles from an extracted directory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ProviderInfo:
    """Identity metadata for the translation provider in the bundle."""

    name: str
    model_family: str
    format: str
    version: str | None = None


@dataclass(slots=True)
class LanguagePair:
    """A source→target language pair covered by the bundle."""

    source: str
    target: str


@dataclass(slots=True)
class ModelFile:
    """One model file listed in the bundle manifest."""

    path: str
    sha256: str
    size_bytes: int | None = None


@dataclass(slots=True)
class LicenseInfo:
    """License and attribution metadata from the manifest."""

    name: str
    verification_status: str  # "verified" | "operator_required"
    source_url: str | None = None
    attribution: str | None = None


@dataclass(slots=True)
class TranslationModelManifest:
    """Parsed representation of a translation model bundle ``manifest.json``.

    Provides structured access to provider identity, supported language pairs,
    file inventory, and expected runtime environment.
    """

    bundle_version: str
    tomorrowland_release: str
    created_at: str
    provider: ProviderInfo
    supported_languages: list[str]
    language_pairs: list[LanguagePair]
    models_dir: str
    expected_env: dict[str, str]
    files: list[ModelFile]
    license: LicenseInfo | None = None

    # -- Convenience queries -----------------------------------------------

    @property
    def language_pair_set(self) -> set[tuple[str, str]]:
        """Return the set of (source, target) tuples covered by the bundle."""
        return {(p.source, p.target) for p in self.language_pairs}

    @property
    def file_paths(self) -> set[str]:
        """Return the set of relative file paths listed in the manifest."""
        return {f.path for f in self.files}

    def checksum_for(self, relative_path: str) -> str | None:
        """Return the expected SHA-256 for *relative_path*, or None."""
        for f in self.files:
            if f.path == relative_path:
                return f.sha256
        return None

    def supports_pair(self, source: str, target: str) -> bool:
        """Return True when the bundle covers *source*→*target*."""
        return (source, target) in self.language_pair_set

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to a dict matching the manifest schema."""
        result: dict[str, Any] = {
            "bundle_version": self.bundle_version,
            "tomorrowland_release": self.tomorrowland_release,
            "created_at": self.created_at,
            "provider": {
                "name": self.provider.name,
                "version": self.provider.version,
                "model_family": self.provider.model_family,
                "format": self.provider.format,
            },
            "supported_languages": sorted(self.supported_languages),
            "language_pairs": [
                {"source": p.source, "target": p.target}
                for p in sorted(self.language_pairs, key=lambda p: (p.source, p.target))
            ],
            "models_dir": self.models_dir,
            "expected_env": dict(self.expected_env),
            "files": sorted(
                [
                    {
                        "path": f.path,
                        "sha256": f.sha256,
                        **({"size_bytes": f.size_bytes} if f.size_bytes is not None else {}),
                    }
                    for f in self.files
                ],
                key=lambda x: x["path"],
            ),
        }
        if self.license is not None:
            result["license"] = {
                "name": self.license.name,
                "source_url": self.license.source_url,
                "attribution": self.license.attribution,
                "verification_status": self.license.verification_status,
            }
        return result


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------


def parse_manifest(raw: dict[str, Any]) -> TranslationModelManifest:
    """Parse a raw manifest dict into a :class:`TranslationModelManifest`.

    Performs structural validation (required fields, types) but does **not**
    validate file existence or checksums — use :class:`BundleValidator` for
    that.

    Raises :exc:`ValueError` when required fields are missing or have
    incorrect types.
    """
    _require_keys(raw, "bundle_version", "tomorrowland_release", "created_at")
    _require_keys(
        raw,
        "provider",
        "supported_languages",
        "language_pairs",
        "models_dir",
        "expected_env",
        "files",
    )

    provider_raw = raw["provider"]
    if not isinstance(provider_raw, dict):
        raise ValueError("'provider' must be an object")
    _require_keys(provider_raw, "name", "model_family", "format")
    version_raw = provider_raw.get("version")
    if version_raw is not None and not isinstance(version_raw, str):
        raise ValueError(
            f"'provider.version' must be a string or null, got {type(version_raw).__name__}"
        )
    provider = ProviderInfo(
        name=_str_val(provider_raw, "name"),
        model_family=_str_val(provider_raw, "model_family"),
        format=_str_val(provider_raw, "format"),
        version=version_raw,
    )

    languages = raw["supported_languages"]
    if not isinstance(languages, list) or not languages:
        raise ValueError("'supported_languages' must be a non-empty array")
    if not all(isinstance(lang, str) for lang in languages):
        raise ValueError("'supported_languages' must contain only strings")

    pairs_raw = raw["language_pairs"]
    if not isinstance(pairs_raw, list) or not pairs_raw:
        raise ValueError("'language_pairs' must be a non-empty array")
    pairs: list[LanguagePair] = []
    for item in pairs_raw:
        if not isinstance(item, dict):
            raise ValueError("each language_pairs entry must be an object")
        _require_keys(item, "source", "target")
        pairs.append(LanguagePair(source=_str_val(item, "source"), target=_str_val(item, "target")))

    models_dir = _str_val(raw, "models_dir")

    env_raw = raw["expected_env"]
    if not isinstance(env_raw, dict):
        raise ValueError("'expected_env' must be an object")
    expected_env = {str(k): str(v) for k, v in env_raw.items()}

    files_raw = raw["files"]
    if not isinstance(files_raw, list) or not files_raw:
        raise ValueError("'files' must be a non-empty array")
    model_files: list[ModelFile] = []
    for item in files_raw:
        if not isinstance(item, dict):
            raise ValueError("each files entry must be an object")
        _require_keys(item, "path", "sha256")
        size = item.get("size_bytes")
        if size is not None and not isinstance(size, int):
            raise ValueError(f"files[].size_bytes must be an integer, got {type(size).__name__}")
        model_files.append(
            ModelFile(
                path=_str_val(item, "path"),
                sha256=_str_val(item, "sha256"),
                size_bytes=size,
            )
        )

    license_info: LicenseInfo | None = None
    if "license" in raw:
        lic_raw = raw["license"]
        if not isinstance(lic_raw, dict):
            raise ValueError("'license' must be an object")
        _require_keys(lic_raw, "name", "verification_status")
        license_info = LicenseInfo(
            name=_str_val(lic_raw, "name"),
            verification_status=_str_val(lic_raw, "verification_status"),
            source_url=lic_raw.get("source_url"),
            attribution=lic_raw.get("attribution"),
        )

    return TranslationModelManifest(
        bundle_version=_str_val(raw, "bundle_version"),
        tomorrowland_release=_str_val(raw, "tomorrowland_release"),
        created_at=_str_val(raw, "created_at"),
        provider=provider,
        supported_languages=languages,
        language_pairs=pairs,
        models_dir=models_dir,
        expected_env=expected_env,
        files=model_files,
        license=license_info,
    )


def load_manifest_from_path(manifest_path: str | Path) -> TranslationModelManifest:
    """Load and parse a ``manifest.json`` from *manifest_path*.

    Combines file reading with :func:`parse_manifest`.
    """
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest.json must contain a JSON object at the root")
    return parse_manifest(raw)


# ---------------------------------------------------------------------------
# Bundle validation
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BundleIntegrityReport:
    """Result of validating a bundle against its manifest."""

    valid: bool
    manifest: TranslationModelManifest
    missing_files: list[str] = field(default_factory=list)
    checksum_mismatches: list[str] = field(default_factory=list)
    extra_unlisted_files: list[str] = field(default_factory=list)

    @property
    def issues(self) -> list[str]:
        """All validation issues concatenated."""
        return [
            *[f"missing: {path}" for path in self.missing_files],
            *[f"checksum mismatch: {path}" for path in self.checksum_mismatches],
            *[f"extra unlisted file: {path}" for path in self.extra_unlisted_files],
        ]


class BundleValidator:
    """Validate an extracted translation model bundle against its manifest.

    Checks that every file listed in the manifest exists on disk and matches
    its expected SHA-256 checksum.  Optionally warns about extra files in the
    models directory that are not listed in the manifest.
    """

    def __init__(self, manifest: TranslationModelManifest, bundle_root: str | Path) -> None:
        self._manifest = manifest
        self._root = Path(bundle_root)

    @property
    def manifest(self) -> TranslationModelManifest:
        return self._manifest

    def validate(self, *, strict_extra_files: bool = False) -> BundleIntegrityReport:
        """Run all integrity checks and return a :class:`BundleIntegrityReport`.

        When *strict_extra_files* is True, any file under ``models_dir`` that
        is not listed in the manifest is reported as an issue (but does not
        invalidate the bundle by itself).
        """
        missing: list[str] = []
        mismatch: list[str] = []
        extra: list[str] = []

        models_root = self._root / self._manifest.models_dir

        for f in self._manifest.files:
            disk_path = self._root / f.path
            if not disk_path.is_file():
                missing.append(f.path)
                continue
            actual = _sha256_file(disk_path)
            if actual != f.sha256:
                mismatch.append(f.path)

        if strict_extra_files and models_root.is_dir():
            listed: set[str] = {f.path for f in self._manifest.files}
            for disk_file in models_root.rglob("*"):
                if disk_file.is_file():
                    rel = disk_file.relative_to(self._root).as_posix()
                    if rel not in listed:
                        extra.append(rel)

        valid = not missing and not mismatch
        return BundleIntegrityReport(
            valid=valid,
            manifest=self._manifest,
            missing_files=missing,
            checksum_mismatches=mismatch,
            extra_unlisted_files=extra,
        )

    def health(self) -> dict[str, Any]:
        """Return a health-check snapshot suitable for :meth:`TranslationProvider.health`.

        Example::

            {
                "status": "healthy",
                "bundle_valid": true,
                "provider": "argos",
                "version": "libretranslate-1.6.3",
                "model_family": "argos",
                "supported_languages": ["ar", "en", ...],
                "language_pairs": 32,
                "files_present": 32,
                "files_expected": 32,
                "issues": [],
            }
        """
        report = self.validate()
        return {
            "status": "healthy" if report.valid else "unhealthy",
            "bundle_valid": report.valid,
            "provider": self._manifest.provider.name,
            "version": self._manifest.provider.version,
            "model_family": self._manifest.provider.model_family,
            "supported_languages": sorted(self._manifest.supported_languages),
            "language_pairs": len(self._manifest.language_pairs),
            "files_present": len(self._manifest.files) - len(report.missing_files),
            "files_expected": len(self._manifest.files),
            "issues": report.issues,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of *path*."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_keys(d: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if key not in d:
            raise ValueError(f"missing required key: '{key}'")


def _str_val(d: dict[str, Any], key: str) -> str:
    val = d[key]
    if not isinstance(val, str):
        raise ValueError(f"'{key}' must be a string, got {type(val).__name__}")
    return val
