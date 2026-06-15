from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by Phase 01 service skeletons."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "0.6.0"
    build_commit: str = "unknown"
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    postgres_url: str = "postgresql+psycopg://postgres:changeme@postgres:5432/app"
    redis_url: str = "redis://redis:6379/0"
    kafka_broker: str = "kafka:9092"
    qdrant_url: str = "http://qdrant:6333"
    files_root: Path = Path("/data")
    jwt_secret: str = "change-me-in-production"
    cors_origins: str = "http://localhost:8080"

    libretranslate_url: str = "http://libretranslate:5000"

    ollama_url: str = "http://ollama-llm:11434"
    ollama_model: str = "qwen3:4b"
    # Optional smaller model for cheap repeated tasks (query rewrite, auto-tag,
    # key-points augmentation, chunk-level summary map). Falls back to
    # ollama_model when empty.
    ollama_utility_model: str = "qwen3:1.7b"
    # Optional dedicated model for cross-encoder reranking. Falls back to
    # effective_utility_model (and then ollama_model) when empty.
    # Also readable as RERANK_MODEL (future dedicated reranking pipeline).
    ollama_reranker_model: str = Field(
        default="",
        validation_alias=AliasChoices("rerank_model", "ollama_reranker_model"),
    )

    @property
    def effective_utility_model(self) -> str:
        """Model to use for cheap/repeated tasks. Falls back to main model."""
        return self.ollama_utility_model or self.ollama_model

    @property
    def effective_reranker_model(self) -> str:
        """Model to use for reranking. Falls back through utility to main."""
        return self.ollama_reranker_model or self.effective_utility_model

    # Credential store encryption key.  When empty, a dev-only fallback is used
    # (credentials are still encrypted in the DB but the key is deterministic).
    credential_store_key: str = ""

    # MCP adapter settings (#560)
    tomorrowland_api_url: str = "http://localhost:8000"
    tomorrowland_api_key: str = ""
    tomorrowland_api_timeout: float = 30.0
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001

    # Researcher API usage limits (#561)
    # Set AGENT_RATE_LIMIT_ENABLED=false to disable (dev/test only).
    agent_rate_limit_enabled: bool = True
    agent_rate_limit_window_seconds: int = Field(default=60, gt=0)
    agent_rate_limit_calls_per_window: int = Field(default=100, gt=0)
    agent_rate_limit_ask_corpus_calls_per_window: int = Field(default=20, gt=0)

    # LLM generation provider — "ollama" (default), "openai-compatible",
    # "openai", "litellm", or "llama-cpp".
    # LLM_BASE_URL overrides OLLAMA_URL when set; LLM_MODEL overrides OLLAMA_MODEL.
    # LLM_API_KEY is used for OpenAI-compatible providers that require Bearer auth.
    llm_provider: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""

    auth_provider: Literal["local", "ldap", "both"] = "both"
    ldap_url: str = "ldap://domain-controller:389"
    ldap_base_dn: str = "DC=company,DC=local"
    ldap_bind_user: str = "cn=svc-search,DC=company,DC=local"
    ldap_bind_password: str = "changeme"

    # LDAP group search (#582).  Admin-only live search; results are never persisted
    # unless the admin explicitly maps a group.
    ldap_group_search_base_dns: str = ""
    ldap_group_search_filter: str = "(&(objectClass=group)(cn=*{query}*))"
    ldap_group_search_limit: int = Field(default=50, ge=1, le=200)
    ldap_group_search_timeout: float = Field(default=10.0, ge=1.0, le=30.0)
    ldap_group_external_id_attr: str = "objectGUID"
    ldap_group_display_name_attr: str = "cn"

    @property
    def ldap_group_search_base_dn_list(self) -> list[str]:
        """Return the configured group search base DNs as a list."""
        if not self.ldap_group_search_base_dns:
            return [self.ldap_base_dn]
        return [dn.strip() for dn in self.ldap_group_search_base_dns.split(",") if dn.strip()]

    # --- Extraction feature flags ---
    # Requires tesseract-ocr + poppler-utils in PATH (or Docker image).
    enable_ocr: bool = False
    # Requires LibreOffice (soffice) in PATH.
    enable_legacy_office: bool = False
    # Use native Markdown converters for DOCX/PPTX/XLSX → structured extraction.
    enable_markitdown: bool = True
    # Use Docling for layout-aware PDF extraction (tables, multi-column, headings).
    # Requires ``pip install docling`` (or the [docling] optional extra).
    enable_docling: bool = False
    # Auto-detect source_language when not provided by the connector.
    enable_language_detection: bool = True

    # --- Preview rendering (#539) ---
    # Gates preview_render job dispatch; the manifest endpoint itself stays
    # available and reports a text fallback when disabled.
    enable_preview_render: bool = True
    preview_max_file_bytes: int = Field(default=104_857_600, ge=1)
    preview_max_inline_images: int = Field(default=50, ge=0)
    preview_max_inline_image_bytes: int = Field(default=5_242_880, ge=1)
    # LibreOffice Office→PDF conversion (preview worker only).
    preview_render_timeout_seconds: float = Field(default=120.0, gt=0)
    preview_max_pages: int = Field(default=500, ge=1)
    # Spreadsheet preview grid caps (per sheet). A preview shows the first
    # rows/cols; the full sheet remains available via download.
    preview_max_sheet_rows: int = Field(default=200, ge=1)
    preview_max_sheet_cols: int = Field(default=50, ge=1)

    feature_rag_qa: bool = True
    rag_max_chunks: int = Field(default=5, ge=1, le=50)
    rag_max_tokens_context: int = Field(default=2000, ge=100)
    rag_score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    feature_summarization: bool = True
    feature_entity_extraction: bool = True
    feature_annotations: bool = True
    feature_subscriptions: bool = True
    feature_expertise_map: bool = True
    feature_related_docs: bool = True
    feature_auto_tagging: bool = True
    feature_document_chat: bool = True
    feature_document_chat_query_rewrite: bool = True
    feature_document_chat_reranker: bool = True
    feature_document_chat_metadata_search: bool = True
    feature_document_chat_translated_text: bool = True
    feature_document_chat_hierarchy_expansion: bool = False
    feature_document_chat_coarse_to_fine_routing: bool = False
    feature_document_chat_streaming: bool = True
    # Enable local-dev LLM documentation & model recommendations for CPU-only
    # machines with limited RAM (e.g. 16GB, no discrete GPU). Default: false
    feature_local_llm_dev: bool = False
    auto_enrich_threshold: int = Field(default=5, ge=0)

    embedding_provider: str = ""
    # Also readable as OLLAMA_EMBED_MODEL.
    embedding_model: str = Field(
        default="qwen3-embedding:8b",
        validation_alias=AliasChoices("ollama_embed_model", "embedding_model"),
    )
    embedding_url: str = ""
    # Optional API key for OpenAI-compatible embedding providers.
    embedding_api_key: str = ""
    # Also readable as EMBEDDING_DIM.
    embedding_dimension: int = Field(
        default=4096,
        validation_alias=AliasChoices("embedding_dim", "embedding_dimension"),
    )
    embedding_max_tokens: int = 1024
    embedding_timeout: float = 180.0
    # Short timeout used specifically during the search request path so that a
    # slow/unavailable embedding service degrades to lexical-only results rather
    # than blocking until nginx times out (110 s). Kept well below nginx's read
    # timeout; the existing fallback in search.py catches the exception and
    # continues with BM25-only results.
    search_embedding_timeout: float = 5.0
    embedding_provider_unsafe_allow_test_in_prod: bool = False

    # --- Search reranker (BGE / cross-encoder) ---
    # When enabled, the top search_reranker_depth results from the hybrid merge
    # are re-scored and re-sorted by a cross-encoder reranker.
    search_reranker_enabled: bool = False
    # Number of top candidates (after merge) to send to the reranker.
    search_reranker_depth: int = Field(default=20, ge=1, le=200)
    # URL of a TEI-compatible /rerank endpoint.
    # When set, the endpoint-based reranker is used (preferred for BGE models).
    # When empty but search_reranker_enabled is True, falls back to Ollama
    # prompt-based reranking via ollama_reranker_model.
    search_reranker_url: str = ""
    # Model name sent to the /rerank endpoint.
    search_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # Minimum relevance score (0-1) to keep a result after reranking.
    search_reranker_min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    # HTTP timeout for the /rerank call.
    search_reranker_timeout: float = 10.0

    meilisearch_url: str = "http://meilisearch:7700"
    meilisearch_master_key: str = ""
    meilisearch_search_key: str = ""
    feature_meilisearch_search: bool = True
    feature_meilisearch_shadow_index: bool = False
    # Maximum time create_app will block waiting for Meilisearch to apply
    # initial index settings (filterableAttributes, searchableAttributes,
    # etc.) before serving search traffic. The server-side apply is async,
    # so without this wait a cold-start request can fail with errors like
    # ``attribute is not filterable``.
    meili_settings_readiness_timeout_s: float = 30.0

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_user: str = "tomorrowland"
    rabbitmq_pass: str = "changeme"
    rabbitmq_enabled: bool = True

    supported_translation_source_languages: str = "en,he,zh,ko,th,ar,fr,ru,es"

    # --- Translation model bundle (#730) ---
    # Path to an extracted translation model bundle directory containing
    # manifest.json and model files. When set, translation providers that
    # support local model loading will validate and load models from this
    # path at startup. Leave empty when models are baked into the provider
    # Docker image (as with the default LibreTranslate Argos setup).
    translation_model_bundle_path: str = ""

    # --- High-quality translation provider (#731) ---
    # Path to an extracted translation model bundle for the high-quality
    # provider (OPUS-MT via CTranslate2). When set and the bundle contains
    # models for the requested language pair, the slow/enrich worker uses
    # this provider instead of the LibreTranslate Argos baseline.
    # Falls back silently to the baseline when the bundle is missing,
    # unhealthy, or doesn't cover the requested language pair.
    # Requires: pip install tomorrowland[ctranslate2]
    translation_high_provider_bundle_path: str = ""

    # --- Translation quality estimation (#733) ---
    # Enable offline, reference-free quality estimation for translation
    # versions.  When enabled the enrich worker scores translated segments
    # after a version becomes available and stores the results in
    # translation-version metadata.
    # Disabled by default — no QE model is required for normal operation.
    translation_qe_enabled: bool = False
    # Path to a local QE model directory or file.  When set and
    # translation_qe_enabled is True, the provider loads the model;
    # when empty, a simple heuristic scorer is used for testing.
    translation_qe_model_path: str = ""
    # Segments scoring below this threshold (0.0–1.0) are flagged as
    # "low score" and included in version metadata warnings.
    translation_qe_low_score_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins from a comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def supported_translation_source_languages_list(self) -> list[str]:
        """Return supported source languages parsed from the comma-separated setting."""
        return [
            lang.strip()
            for lang in self.supported_translation_source_languages.split(",")
            if lang.strip()
        ]


def get_settings() -> Settings:
    """Return settings loaded from the current environment."""
    return Settings()
