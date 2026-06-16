"""Typed registry of admin-manageable runtime settings (#812).

The registry declares a curated, *safe* subset of the Pydantic ``Settings``
(``shared.config.Settings``) that admins may inspect — and, for explicitly
runtime-editable entries, override from the UI.  It deliberately does **not**
expose every raw environment variable.

Precedence model (explicit and tested):

    deployment-locked env  >  database override  >  env value  >  app default

A setting that is *not* ``is_runtime_editable`` is treated as deployment-locked:
its effective value always comes from the process environment / application
default and cannot be overridden through the API.  For runtime-editable
settings, a database override (stored in ``admin_runtime_config_overrides``)
takes precedence over the env/default value.

Secrets are never returned in raw form.  A secret entry reports only whether it
is configured, a redacted placeholder, and its source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic_core import PydanticUndefined

from shared.config import Settings

REDACTED = "••••••••"

SettingType = Literal["string", "int", "float", "bool", "enum", "json", "secret"]

# Categories (issue #812 §1).
CATEGORY_GENERAL = "General / deployment"
CATEGORY_AUTH = "Authentication / LDAP"
CATEGORY_EXTRACTION = "Extraction / OCR / Docling"
CATEGORY_PREVIEW = "Preview"
CATEGORY_SEARCH = "Search / reranker / embeddings"
CATEGORY_RAG = "RAG / chat"
CATEGORY_TRANSLATION = "Translation / quality estimation"
CATEGORY_WORKER = "Worker / queue / pipeline"
CATEGORY_OBSERVABILITY = "Observability / logging"
CATEGORY_LLM = "Model providers / LLM runtime"
CATEGORY_AIRGAP = "Air-gapped packaging / runtime"

PRECEDENCE = "deployment-locked env > database override > env value > application default"


@dataclass(frozen=True)
class ConfigSetting:
    """Metadata describing a single admin-manageable setting."""

    key: str
    category: str
    display_name: str
    description: str
    type: SettingType
    is_secret: bool = False
    is_sensitive: bool = False
    is_runtime_editable: bool = False
    requires_restart: bool = False
    requires_worker_restart: bool = False
    requires_reindex: bool = False
    requires_resync: bool = False
    enum_values: tuple[str, ...] | None = None
    min_value: float | None = None
    max_value: float | None = None


def _s(*args: Any, **kwargs: Any) -> ConfigSetting:
    return ConfigSetting(*args, **kwargs)


# Curated registry.  Editable entries are non-secret scalars; secrets are always
# read-only and redacted.  ``requires_*`` flags are truthful about what it takes
# for a stored value to take effect (most settings are read at process startup).
CONFIG_REGISTRY: tuple[ConfigSetting, ...] = (
    # --- General / deployment ---
    _s(
        "app_env",
        CATEGORY_GENERAL,
        "Application environment",
        "Deployment environment. Read at startup and used across services.",
        "enum",
        enum_values=("dev", "test", "prod"),
        requires_restart=True,
    ),
    _s(
        "app_version",
        CATEGORY_GENERAL,
        "Application version",
        "Reported version string. Read-only, set at build time.",
        "string",
    ),
    _s(
        "files_root",
        CATEGORY_GENERAL,
        "Files root",
        "Filesystem root for stored documents. Deployment-locked.",
        "string",
        requires_restart=True,
    ),
    _s(
        "cors_origins",
        CATEGORY_GENERAL,
        "CORS origins",
        "Comma-separated list of allowed CORS origins.",
        "string",
        is_runtime_editable=True,
        requires_restart=True,
    ),
    # --- Observability / logging ---
    _s(
        "log_level",
        CATEGORY_OBSERVABILITY,
        "Log level",
        "Minimum log level emitted by services.",
        "enum",
        enum_values=("critical", "error", "warning", "info", "debug"),
        is_runtime_editable=True,
        requires_restart=True,
    ),
    # --- Authentication / LDAP ---
    _s(
        "auth_provider",
        CATEGORY_AUTH,
        "Auth provider",
        "Authentication backend(s) enabled. Deployment-locked.",
        "enum",
        enum_values=("local", "ldap", "both"),
        requires_restart=True,
    ),
    _s(
        "ldap_url",
        CATEGORY_AUTH,
        "LDAP URL",
        "LDAP/AD server URL. Deployment-locked.",
        "string",
        is_sensitive=True,
        requires_restart=True,
    ),
    _s(
        "ldap_bind_password",
        CATEGORY_AUTH,
        "LDAP bind password",
        "Service-account password used to bind to LDAP.",
        "secret",
        is_secret=True,
        is_sensitive=True,
        requires_restart=True,
    ),
    _s(
        "ldap_group_search_limit",
        CATEGORY_AUTH,
        "LDAP group search limit",
        "Maximum LDAP group-search results returned to admins.",
        "int",
        is_runtime_editable=True,
        min_value=1,
        max_value=200,
    ),
    # --- Extraction / OCR / Docling ---
    _s(
        "enable_ocr",
        CATEGORY_EXTRACTION,
        "Enable OCR",
        "Run OCR on scanned PDFs/images during extraction.",
        "bool",
        is_runtime_editable=True,
        requires_worker_restart=True,
    ),
    _s(
        "enable_docling",
        CATEGORY_EXTRACTION,
        "Enable Docling",
        "Use Docling for layout-aware PDF extraction.",
        "bool",
        is_runtime_editable=True,
        requires_worker_restart=True,
    ),
    _s(
        "enable_language_detection",
        CATEGORY_EXTRACTION,
        "Enable language detection",
        "Auto-detect source language when not supplied by the connector.",
        "bool",
        is_runtime_editable=True,
        requires_worker_restart=True,
    ),
    # --- Preview ---
    _s(
        "enable_preview_render",
        CATEGORY_PREVIEW,
        "Enable preview rendering",
        "Gate dispatch of preview-render jobs.",
        "bool",
        is_runtime_editable=True,
        requires_worker_restart=True,
    ),
    _s(
        "preview_max_pages",
        CATEGORY_PREVIEW,
        "Preview max pages",
        "Maximum pages rendered for a document preview.",
        "int",
        is_runtime_editable=True,
        min_value=1,
    ),
    _s(
        "preview_max_file_bytes",
        CATEGORY_PREVIEW,
        "Preview max file bytes",
        "Maximum source file size eligible for preview rendering.",
        "int",
        is_runtime_editable=True,
        min_value=1,
    ),
    # --- Search / reranker / embeddings ---
    _s(
        "search_reranker_enabled",
        CATEGORY_SEARCH,
        "Reranker enabled",
        "Re-score top hybrid results with a cross-encoder reranker.",
        "bool",
        is_runtime_editable=True,
    ),
    _s(
        "search_reranker_depth",
        CATEGORY_SEARCH,
        "Reranker depth",
        "Number of top candidates sent to the reranker.",
        "int",
        is_runtime_editable=True,
        min_value=1,
        max_value=200,
    ),
    _s(
        "search_reranker_min_score",
        CATEGORY_SEARCH,
        "Reranker minimum score",
        "Minimum relevance score (0-1) kept after reranking.",
        "float",
        is_runtime_editable=True,
        min_value=0.0,
        max_value=1.0,
    ),
    _s(
        "embedding_model",
        CATEGORY_SEARCH,
        "Embedding model",
        "Embedding model name. Changing it requires a full reindex.",
        "string",
        requires_restart=True,
        requires_reindex=True,
    ),
    _s(
        "embedding_api_key",
        CATEGORY_SEARCH,
        "Embedding API key",
        "API key for OpenAI-compatible embedding providers.",
        "secret",
        is_secret=True,
        is_sensitive=True,
        requires_restart=True,
    ),
    # --- RAG / chat ---
    _s(
        "feature_rag_qa",
        CATEGORY_RAG,
        "RAG question answering",
        "Enable corpus-level RAG question answering.",
        "bool",
        is_runtime_editable=True,
    ),
    _s(
        "rag_max_chunks",
        CATEGORY_RAG,
        "RAG max chunks",
        "Maximum retrieved chunks used to build RAG context.",
        "int",
        is_runtime_editable=True,
        min_value=1,
        max_value=50,
    ),
    _s(
        "rag_score_threshold",
        CATEGORY_RAG,
        "RAG score threshold",
        "Minimum retrieval score (0-1) for a chunk to enter context.",
        "float",
        is_runtime_editable=True,
        min_value=0.0,
        max_value=1.0,
    ),
    _s(
        "feature_document_chat",
        CATEGORY_RAG,
        "Document chat",
        "Enable per-document chat sessions.",
        "bool",
        is_runtime_editable=True,
    ),
    # --- Translation / quality estimation ---
    _s(
        "translation_qe_enabled",
        CATEGORY_TRANSLATION,
        "Quality estimation",
        "Score translated segments with offline quality estimation.",
        "bool",
        is_runtime_editable=True,
        requires_worker_restart=True,
    ),
    _s(
        "translation_qe_low_score_threshold",
        CATEGORY_TRANSLATION,
        "QE low-score threshold",
        "Segments scoring below this (0-1) are flagged as low score.",
        "float",
        is_runtime_editable=True,
        min_value=0.0,
        max_value=1.0,
    ),
    _s(
        "supported_translation_source_languages",
        CATEGORY_TRANSLATION,
        "Supported source languages",
        "Comma-separated source languages offered for translation.",
        "string",
        is_runtime_editable=True,
        requires_restart=True,
    ),
    # --- Worker / queue / pipeline ---
    _s(
        "rabbitmq_enabled",
        CATEGORY_WORKER,
        "RabbitMQ enabled",
        "Use the RabbitMQ job bus. Deployment-locked.",
        "bool",
        requires_worker_restart=True,
    ),
    _s(
        "rabbitmq_pass",
        CATEGORY_WORKER,
        "RabbitMQ password",
        "RabbitMQ broker password.",
        "secret",
        is_secret=True,
        is_sensitive=True,
        requires_worker_restart=True,
    ),
    _s(
        "auto_enrich_threshold",
        CATEGORY_WORKER,
        "Auto-enrich threshold",
        "Subscriber count above which documents are auto-enriched.",
        "int",
        is_runtime_editable=True,
        min_value=0,
    ),
    # --- Model providers / LLM runtime ---
    _s(
        "llm_provider",
        CATEGORY_LLM,
        "LLM provider",
        "Generation provider id. Deployment-locked.",
        "string",
        requires_restart=True,
    ),
    _s(
        "llm_model",
        CATEGORY_LLM,
        "LLM model",
        "Generation model name. Deployment-locked.",
        "string",
        requires_restart=True,
    ),
    _s(
        "llm_api_key",
        CATEGORY_LLM,
        "LLM API key",
        "Bearer key for OpenAI-compatible generation providers.",
        "secret",
        is_secret=True,
        is_sensitive=True,
        requires_restart=True,
    ),
    _s(
        "ollama_url",
        CATEGORY_LLM,
        "Ollama URL",
        "Base URL of the Ollama runtime. Deployment-locked.",
        "string",
        requires_restart=True,
    ),
    # --- Air-gapped packaging / runtime ---
    _s(
        "translation_model_bundle_path",
        CATEGORY_AIRGAP,
        "Translation model bundle path",
        "Path to an extracted translation model bundle. Deployment-locked.",
        "string",
        requires_worker_restart=True,
    ),
    _s(
        "credential_store_key",
        CATEGORY_AIRGAP,
        "Credential store key",
        "Encryption key for the credential store.",
        "secret",
        is_secret=True,
        is_sensitive=True,
        requires_restart=True,
    ),
)

_REGISTRY_BY_KEY: dict[str, ConfigSetting] = {s.key: s for s in CONFIG_REGISTRY}


def get_setting(key: str) -> ConfigSetting | None:
    """Return the registry entry for *key*, or None when unknown (fail closed)."""
    return _REGISTRY_BY_KEY.get(key)


def _coerce(value: Any) -> Any:
    """Normalise a Settings value to a JSON-friendly scalar."""
    if isinstance(value, Path):
        return str(value)
    return value


def _field_default(key: str) -> Any:
    pyd_field = Settings.model_fields.get(key)
    if pyd_field is None:
        return None
    default = pyd_field.default
    if default is PydanticUndefined:
        return None
    return _coerce(default)


class ValidationError(ValueError):
    """Raised when a proposed override value fails registry validation."""


def _check_range(setting: ConfigSetting, value: float) -> None:
    if setting.min_value is not None and value < setting.min_value:
        raise ValidationError(f"{setting.key} must be >= {setting.min_value}")
    if setting.max_value is not None and value > setting.max_value:
        raise ValidationError(f"{setting.key} must be <= {setting.max_value}")


def coerce_and_validate(setting: ConfigSetting, raw: Any) -> Any:
    """Validate and coerce *raw* against the registry metadata.

    Raises ``ValidationError`` for type/range/enum violations. Secrets are never
    editable through this path.
    """
    if not setting.is_runtime_editable:
        raise ValidationError(f"{setting.key} is not runtime-editable")
    if setting.is_secret:
        raise ValidationError(f"{setting.key} is a secret and cannot be edited here")

    t = setting.type
    if t == "bool":
        if not isinstance(raw, bool):
            raise ValidationError(f"{setting.key} expects a boolean")
        return raw
    if t == "int":
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValidationError(f"{setting.key} expects an integer")
        _check_range(setting, raw)
        return raw
    if t == "float":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValidationError(f"{setting.key} expects a number")
        value = float(raw)
        _check_range(setting, value)
        return value
    if t == "enum":
        if raw not in (setting.enum_values or ()):
            allowed = ", ".join(setting.enum_values or ())
            raise ValidationError(f"{setting.key} must be one of: {allowed}")
        return raw
    if t == "string":
        if not isinstance(raw, str):
            raise ValidationError(f"{setting.key} expects a string")
        return raw
    if t == "json":
        return raw
    raise ValidationError(f"{setting.key} has unsupported type {t}")


def describe_setting(
    setting: ConfigSetting,
    settings: Settings,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the API representation of a setting, redacting secrets.

    *override* is a row dict (``value``/``updated_at``/``version``) from the
    overrides repository, or None.
    """
    base: dict[str, Any] = {
        "key": setting.key,
        "category": setting.category,
        "display_name": setting.display_name,
        "description": setting.description,
        "type": setting.type,
        "is_secret": setting.is_secret,
        "is_sensitive": setting.is_sensitive,
        "is_runtime_editable": setting.is_runtime_editable,
        "requires_restart": setting.requires_restart,
        "requires_worker_restart": setting.requires_worker_restart,
        "requires_reindex": setting.requires_reindex,
        "requires_resync": setting.requires_resync,
        "enum_values": list(setting.enum_values) if setting.enum_values else None,
        "min_value": setting.min_value,
        "max_value": setting.max_value,
        "override_present": False,
        "override_updated_at": None,
    }

    configured = _coerce(getattr(settings, setting.key, None))

    if setting.is_secret:
        # Never expose raw secret values.
        is_configured = bool(configured)
        base["configured"] = is_configured
        base["safe_default"] = None
        base["configured_value"] = REDACTED if is_configured else None
        base["current_effective_value"] = REDACTED if is_configured else None
        base["source"] = "env" if is_configured else "default"
        return base

    default = _field_default(setting.key)
    base["safe_default"] = default
    base["configured_value"] = configured

    if setting.is_runtime_editable and override is not None:
        base["current_effective_value"] = override.get("value")
        base["source"] = "database_override"
        base["override_present"] = True
        base["override_updated_at"] = override.get("updated_at")
    else:
        base["current_effective_value"] = configured
        base["source"] = "env" if configured != default else "default"
    return base
