"""Intelligence services for local LLM-powered document analysis."""

from services.intelligence.credential_store import CredentialStore, mask_credential
from services.intelligence.factory import build_llm_provider
from services.intelligence.llm_provider import LLMProvider, OpenAICompatibleLLMProvider
from services.intelligence.ollama_client import OllamaClient
from services.intelligence.profile_repository import ProfileRepository
from services.intelligence.provider_registry import ProviderRegistry
from services.intelligence.repository import IntelligenceRepository
from services.intelligence.source_qa_repository import SourceQACheck, SourceQARepository
from services.intelligence.source_qa_service import get_latest_qa, run_source_qa
from services.intelligence.ssrf_validation import validate_provider_url
from services.intelligence.task_defaults import (
    TaskDefaultResolver,
    TaskResolution,
    build_llm_from_resolution,
)
from services.intelligence.worker import IntelligenceWorker

__all__ = [
    "IntelligenceWorker",
    "IntelligenceRepository",
    "ProfileRepository",
    "LLMProvider",
    "OllamaClient",
    "OpenAICompatibleLLMProvider",
    "SourceQACheck",
    "SourceQARepository",
    "get_latest_qa",
    "run_source_qa",
    "TaskDefaultResolver",
    "TaskResolution",
    "build_llm_from_resolution",
    "build_llm_provider",
    "CredentialStore",
    "ProviderRegistry",
    "mask_credential",
    "validate_provider_url",
]
