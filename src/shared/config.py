from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by Phase 01 service skeletons."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"

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
    feature_summarization: bool = True
    feature_entity_extraction: bool = True
    feature_annotations: bool = True
    feature_subscriptions: bool = True
    feature_expertise_map: bool = True
    feature_related_docs: bool = True
    feature_auto_tagging: bool = True
    auto_enrich_threshold: int = Field(default=5, ge=0)
    ingest_mode: Literal["hybrid", "watch", "poll"] = "hybrid"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins from a comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Return settings loaded from the current environment."""
    return Settings()
