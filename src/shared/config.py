from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by Phase 01 service skeletons."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "0.2.0"
    build_commit: str = "unknown"
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    postgres_url: str = "postgresql+psycopg://postgres:changeme@postgres:5432/app"
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

    # --- Extraction feature flags ---
    # Requires tesseract-ocr + poppler-utils in PATH (or Docker image).
    enable_ocr: bool = False
    # Requires LibreOffice (soffice) in PATH.
    enable_legacy_office: bool = False
    # Use native Markdown converters for DOCX/PPTX/XLSX → structured extraction.
    enable_markitdown: bool = True
    # Auto-detect source_language when not provided by the connector.
    enable_language_detection: bool = True

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
    feature_document_chat_streaming: bool = True
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

    meilisearch_url: str = "http://meilisearch:7700"
    meilisearch_master_key: str = ""
    meilisearch_search_key: str = ""
    feature_meilisearch_search: bool = True
    feature_meilisearch_shadow_index: bool = False

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_user: str = "tomorrowland"
    rabbitmq_pass: str = "changeme"
    rabbitmq_enabled: bool = True

    supported_translation_source_languages: str = "en,he,zh,ko,th,ar,fr,ru,es"

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
