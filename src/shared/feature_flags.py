from __future__ import annotations

from types import MappingProxyType
from typing import Final

JsonValue = bool | int | float | str

SYSTEM_CONFIG_DEFAULTS: Final[MappingProxyType[str, JsonValue]] = MappingProxyType(
    {
        "feature.rag_qa": True,
        "feature.summarization": True,
        "feature.entity_extraction": True,
        "feature.annotations": True,
        "feature.subscriptions": True,
        "feature.expertise_map": True,
        "feature.related_docs": True,
        "feature.auto_tagging": True,
        "feature.document_chat": True,
        "feature.document_chat_metadata_search": True,
        "feature.document_chat_query_rewrite": True,
        "feature.document_chat_reranker": True,
        "feature.document_chat_streaming": True,
        "feature.document_chat_translated_text": True,
        "llm.model": "qwen3:4b",
        "llm.qa_system_prompt": (
            "You are a knowledge assistant. Answer based only on the context provided."
        ),
        "llm.summarization_prompt": "Summarize the following document in 3-5 sentences.",
        "llm.entity_extraction_prompt": (
            "Extract named entities (people, organizations, locations) as JSON."
        ),
        "llm.auto_tag_prompt": (
            "Assign 3-7 short topic tags to the following document as a JSON array."
        ),
        "search.vector_weight": 0.7,
        "search.bm25_weight": 0.3,
        "search.related_docs_limit": 5,
        "auto_enrich.threshold": 5,
        "alerts.similarity_threshold": 0.75,
        "alerts.check_on_ingest": True,
    }
)

ENV_FEATURE_TO_CONFIG_KEY: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "FEATURE_DOCUMENT_CHAT": "feature.document_chat",
        "FEATURE_DOCUMENT_CHAT_QUERY_REWRITE": "feature.document_chat_query_rewrite",
        "FEATURE_DOCUMENT_CHAT_RERANKER": "feature.document_chat_reranker",
        "FEATURE_DOCUMENT_CHAT_METADATA_SEARCH": "feature.document_chat_metadata_search",
        "FEATURE_DOCUMENT_CHAT_TRANSLATED_TEXT": "feature.document_chat_translated_text",
        "FEATURE_DOCUMENT_CHAT_STREAMING": "feature.document_chat_streaming",
        "FEATURE_RAG_QA": "feature.rag_qa",
        "FEATURE_SUMMARIZATION": "feature.summarization",
        "FEATURE_ENTITY_EXTRACTION": "feature.entity_extraction",
        "FEATURE_ANNOTATIONS": "feature.annotations",
        "FEATURE_SUBSCRIPTIONS": "feature.subscriptions",
        "FEATURE_EXPERTISE_MAP": "feature.expertise_map",
        "FEATURE_RELATED_DOCS": "feature.related_docs",
        "FEATURE_AUTO_TAGGING": "feature.auto_tagging",
        "AUTO_ENRICH_THRESHOLD": "auto_enrich.threshold",
    }
)
