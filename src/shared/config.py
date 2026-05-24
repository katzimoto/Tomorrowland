from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by Phase 01 service skeletons."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_version: str = "0.1.0"
    build_commit: str = "unknown"
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"

    postgres_url: str = "postgresql+psycopg://postgres:changeme@postgres:5432/app"
    kafka_broker: str = "kafka:9092"
    elastic_url: str = "http://elasticsearch:9200"
    qdrant_url: str = "http://qdrant:6333"
    files_root: Path = Path("/data")
    jwt_secret: str = "change-me-in-production"
    cors_origins: str = "http://localhost:8080"

    libretranslate_url: str = "http://libretranslate:5000"

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "mistral"

    auth_provider: Literal["local", "ldap", "both"] = "both"
    ldap_url: str = "ldap://domain-controller:389"
    ldap_base_dn: str = "DC=company,DC=local"
    ldap_bind_user: str = "cn=svc-search,DC=company,DC=local"
    ldap_bind_password: str = "changeme"

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
    ingest_mode: Literal["hybrid", "watch", "poll"] = "hybrid"

    embedding_provider: str = ""
    embedding_model: str = "nomic-embed-text"
    embedding_url: str = ""
    embedding_dimension: int = 768
    embedding_max_tokens: int = 1024
    embedding_timeout: float = 180.0
    embedding_provider_unsafe_allow_test_in_prod: bool = False

    meilisearch_url: str = "http://meilisearch:7700"
    meilisearch_master_key: str = ""
    meilisearch_search_key: str = ""
    feature_meilisearch_search: bool = True
    feature_meilisearch_shadow_index: bool = True
    # When true, Meilisearch calls ollama-embed directly during indexing and
    # serves hybrid (BM25 + vector) results natively.  Eliminates embed-worker,
    # vector-worker, and qdrant containers.
    feature_meilisearch_hybrid: bool = False
    meili_embedder_name: str = "default"
    meili_semantic_ratio: float = Field(default=0.5, ge=0.0, le=1.0)

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_user: str = "tomorrowland"
    rabbitmq_pass: str = "changeme"
    rabbitmq_enabled: bool = True

    supported_translation_source_languages: str = "en,he,zh,ko,th,ar,fr,ru,es"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins from a comma-separated setting."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

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
