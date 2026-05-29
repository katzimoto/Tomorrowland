"""Intelligence services for local LLM-powered document analysis."""

from services.intelligence.factory import build_llm_provider
from services.intelligence.llm_provider import LLMProvider, OpenAICompatibleLLMProvider
from services.intelligence.ollama_client import OllamaClient
from services.intelligence.repository import IntelligenceRepository
from services.intelligence.worker import IntelligenceWorker

__all__ = [
    "IntelligenceWorker",
    "IntelligenceRepository",
    "LLMProvider",
    "OllamaClient",
    "OpenAICompatibleLLMProvider",
    "build_llm_provider",
]
