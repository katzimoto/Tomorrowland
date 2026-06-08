# Tomorrowland Services Manifest

Auto-generated inventory of all service directories under `src/services/`.
Each entry lists the service purpose, entry point, key dependencies, and test
location so agents can locate the right module in a single file read.

## Inventory

### alerts
Alert matching service — matches newly indexed documents against user
subscriptions using semantic similarity (cosine distance on embeddings).

- **Entry point:** `src/services/alerts/service.py` (`AlertMatcher`)
- **Router:** `src/services/api/routers/alerts.py`
- **Key deps:** documents, search (encoder)
- **Tests:**
  - `tests/unit/test_alerts_*.py`
  - `tests/integration/test_alerts_api.py`

### annotations
Document annotations (highlights, notes, threaded replies). CRUD for
user annotations on document chunks with reply threading.

- **Entry point:** `src/services/annotations/repository.py` (`AnnotationRepository`)
- **Router:** `src/services/api/routers/annotations.py`
- **Key deps:** auth, permissions, shared (db)
- **Tests:**
  - `tests/unit/test_annotations_unified.py`
  - `tests/integration/test_annotations_api.py`
  - `tests/integration/test_annotations_replies.py`

### api
FastAPI application shell — ASGI entrypoint, CORS middleware, auth
dependency injection, and all REST routers grouped under `/api/`.

- **Entry point:** `src/services/api/asgi.py` (ASGI app), `src/services/api/main.py` (`create_app`)
- **Router hub:** `src/services/api/routers/` (auth, documents, search, chat, agent, alerts,
  annotations, vault, system) + `routers/admin/` (config, ingestion, intelligence,
  jobs, ldap, model_providers, rabbit, sources, source_profiles, sync_runs, users)
- **Key deps:** auth (JWT, LDAP), intelligence (LLM provider), permissions
- **Tests:**
  - `tests/integration/test_*_api.py` (domain-specific)
  - `tests/unit/test_api_*.py`

### auth
User authentication — local credentials (hashed passwords), LDAP
integration, JWT token issuance/validation, and group management.

- **Entry point:** `src/services/auth/service.py` (`AuthService`)
- **Router:** `src/services/api/routers/auth.py`
- **Key deps:** shared (metrics, db)
- **Tests:**
  - `tests/unit/test_auth_service.py`
  - `tests/unit/test_ldap_group_mapping.py`
  - `tests/integration/test_api_auth.py`

### chat
Document Chat — persistent chat sessions and messages scoped to
documents, with conversational query rewriting via LLM.

- **Entry point:** `src/services/chat/__init__.py` (exports `ChatRepository`, `ChatSession`, `ChatMessage`)
- **Router:** `src/services/api/routers/chat.py`
- **Key deps:** intelligence (LLMProvider), auth
- **Tests:**
  - `tests/unit/test_chat_service.py`
  - `tests/unit/test_chat_repository.py`
  - `tests/integration/test_chat_api.py`

### chunking
Token-based text chunking — splits extracted text into overlapping chunks
with sentence-boundary awareness and multi-language support.

- **Entry point:** `src/services/chunking/splitter.py` (`chunk_text`, `resolve_chunk_locations`)
- **Key deps:** none (standalone utility)
- **Tests:** `tests/unit/test_chunking.py`

### connectors
Source connectors — pull documents from external sources (local folder,
NiFi, Atlassian Confluence/Jira, SMB shares). Protocol-based with a
factory registry.

- **Entry point:** `src/services/connectors/factory.py` (`build_connector`),
  `src/services/connectors/base.py` (`SourceConnector` protocol)
- **Key deps:** none (standalone)
- **Tests:**
  - `tests/unit/test_connectors.py`
  - `tests/unit/test_connector_factory.py`
  - `tests/unit/test_folder_connector_logging.py`
  - `tests/unit/test_nifi_connector.py`
  - `tests/unit/test_smb_connector.py`
  - `tests/integration/test_nifi_integration.py`

### documents
Document persistence — CRUD for the `documents` table, ingestion
deduplication (external_id hashing), version families, and user tags.

- **Entry point:** `src/services/documents/repository.py` (`DocumentRepository`),
  `src/services/documents/models.py` (`DocumentRow`)
- **Router:** `src/services/api/routers/documents.py`
- **Key deps:** shared (db)
- **Tests:**
  - `tests/unit/test_document_repository.py`
  - `tests/unit/test_document_repository_metadata.py`
  - `tests/unit/test_document_relationships.py`
  - `tests/unit/test_document_version_families.py`
  - `tests/unit/test_user_document_tags.py`
  - `tests/unit/test_sync_lifecycle.py`
  - `tests/integration/test_document_text_api.py`
  - `tests/integration/test_sync_now_lifecycle.py`

### extraction
Text extraction — extracts plain text from 20+ file formats (PDF, DOCX,
XLSX, PPTX, HTML, EPUB, EML, MSG, ODT, ODS, ODP, RTF, plain text, JSON,
XML, archives). MIME-type-aware registry.

- **Entry point:** `src/services/extraction/registry.py` (`ExtractorRegistry`),
  `src/services/extraction/base.py` (`Extractor`, `ExtractionResult`)
- **Key deps:** none (standalone)
- **Tests:**
  - `tests/unit/test_extraction_*.py` (one per format + registry, mime, charset, etc.)

### health
Shared health-check response type and factory. Not a subdirectory;
single module at `src/services/health.py`.

- **Entry point:** `src/services/health.py` (`health()`)
- **Key deps:** none
- **Tests:** `tests/test_health.py`

### intelligence
LLM integration — provider abstraction (OpenAI-compatible, Ollama), model
profile management, background intelligence workers (summarization,
keywords, categories), and provider registry.

- **Entry point:** `src/services/intelligence/factory.py` (`build_llm_provider`),
  `src/services/intelligence/worker.py` (`IntelligenceWorker`)
- **Admin router:** `src/services/api/routers/admin/intelligence.py`,
  `src/services/api/routers/admin/model_providers.py`,
  `src/services/api/routers/admin/source_profiles.py`,
  `src/services/api/routers/admin/source_qa.py`
- **Key deps:** shared (config)
- **Tests:**
  - `tests/unit/test_intelligence_*.py`
  - `tests/unit/test_llm_provider.py`
  - `tests/unit/test_model_provider_*.py`
  - `tests/unit/test_profile_repository.py`
  - `tests/unit/test_provider_registry.py`
  - `tests/unit/test_source_qa_*.py`
  - `tests/unit/test_task_default_resolver.py`
  - `tests/unit/test_ssrf_validation.py`
  - `tests/integration/test_intelligence_*.py`
  - `tests/integration/test_model_provider_api.py`
  - `tests/integration/test_provider_wiring.py`
  - `tests/integration/test_source_profiles_api.py`

### mcp
MCP server — exposes read-only Tomorrowland researcher tools via the
Model Context Protocol (Streamable HTTP + stdio transport). Proxies
`/api/agent/v1/*` endpoints so MCP clients never touch the database
or search backends directly.

- **Entry point:** `src/services/mcp/server.py` (FastMCP server),
  `src/services/mcp/client.py` (async HTTP client for agent API)
- **Key deps:** httpx
- **Tests:**
  - `tests/unit/test_mcp_server.py`
  - `tests/integration/test_mcp_integration.py`

### ops
Operational utilities — smoke-test bootstrap for production Docker
Compose environments (creates admin user, test sources, etc.).

- **Entry point:** `src/services/ops/smoke_bootstrap.py` (`SmokeBootstrapConfig`)
- **Key deps:** auth, shared (config, db)
- **Tests:** `tests/unit/test_smoke_bootstrap.py`

### permissions
Permission enforcement — admin role check, group-based access control,
source-level and document-level ACL assertions.

- **Entry point:** `src/services/permissions/enforcer.py` (`require_admin`,
  `assert_source_access`, `assert_doc_access`)
- **Key deps:** auth
- **Tests:** `tests/unit/test_permissions.py`

### pipeline
Document ingestion pipeline — multi-stage ingestion with Kafka consumers
and RabbitMQ routing: parse → embed → index (+ optional translate/enrich
stages). Orchestrates extraction, chunking, embedding, and indexing.

- **Entry point:** `src/services/pipeline/worker.py` (`PipelineWorker`),
  `src/services/pipeline/jobs.py` (`PipelineJobRepository`)
- **Key deps:** alerts, chunking, documents, extraction, intelligence, search, connectors
- **Sub-components:**
  - `consumer_base.py` — BaseConsumer (Kafka consumer base)
  - `parse_worker.py` — extraction + language detection
  - `embed_worker.py` — chunking + vector embedding + Qdrant upsert
  - `index_worker.py` — Meilisearch indexing
  - `translate_worker.py` — LibreTranslate via RabbitMQ
  - `translation_worker.py` — durable translate_document job processing
  - `enrich_worker.py` — high-quality re-translation for frequently viewed docs
  - `slow_worker.py` — re-translate + re-chunk + re-index for enrichment
  - `alert_consumer.py` — alert matching on new documents
  - `intelligence_consumer.py` — intelligence task processing
  - `publisher.py` — RabbitMQ message routing
  - `original_store.py` — move connector temp files to durable storage
  - `kafka_consumer.py` — low-level Kafka consumer wrapper
- **Tests:**
  - `tests/unit/test_pipeline_*.py`
  - `tests/unit/test_parse_worker.py`
  - `tests/unit/test_consumer_base.py`
  - `tests/unit/test_consumer_commit.py`
  - `tests/unit/test_slow_worker.py`
  - `tests/unit/test_index_consumer.py`
  - `tests/unit/test_kafka_consumer.py`
  - `tests/unit/test_publisher.py`
  - `tests/unit/test_translation_worker.py`
  - `tests/unit/test_original_store.py`
  - `tests/unit/test_worker_observability.py`
  - `tests/integration/test_pipeline.py`
  - `tests/integration/test_pipeline_e2e.py`
  - `tests/integration/test_chunk_index_pipeline.py`
  - `tests/integration/test_consumer_commit_integration.py`
  - `tests/integration/test_enrichment.py`

### preview
Document preview — generates truncated text/HTML snippets of document
content with view-tracking metrics. Handles archives (ZIP, tar) by
rendering a file listing.

- **Entry point:** `src/services/preview/service.py`
- **Router:** n/a (called by documents router)
- **Key deps:** extraction, pipeline (jobs)
- **Tests:**
  - `tests/unit/test_preview_service.py`
  - `tests/integration/test_preview.py`

### rag
RAG Q&A — retrieve-then-generate question answering over the document
corpus. Retrieves chunks via hybrid search (BM25 + Qdrant vector),
re-ranks, assembles a context window, and streams an LLM response.

- **Entry point:** `src/services/rag/service.py`
- **Key deps:** chat, documents, intelligence (LLMProvider), search
- **Sub-components:**
  - `reranker.py` — relevance scoring before context assembly (LLM, Endpoint, NoOp backends)
  - `trace_models.py` — tracing/citation tracking
- **Tests:**
  - `tests/unit/test_rag_reranker.py`
  - `tests/unit/test_rag_trace.py`
  - `tests/unit/test_rag_citation_location.py`
  - `tests/unit/test_rag_retrieval_eval.py`

### related
Related documents and expertise mapping — finds similar documents via
vector search and builds user expertise signals from annotation/view
behavior.

- **Entry point:** `src/services/related/service.py`
- **Router:** n/a (called by documents router)
- **Key deps:** documents, pipeline (jobs), search
- **Tests:** `tests/integration/test_related_api.py`

### search
Search infrastructure — hybrid search (BM25 via Meilisearch + vector via
Qdrant), text encoding (Ollama, OpenAI-compatible), Meilisearch
management (ACL, backfill, language detection, rollout, settings), and
search result re-ranking (BGE cross-encoder, LLM fallback).

- **Entry point:** `src/services/search/factory.py` (`build_encoder`, `build_reranker`),
  `src/services/search/hybrid.py` (`merge_results`)
- **Router:** `src/services/api/routers/search.py`
- **Key deps:** shared (config), chunking
- **Tests:**
  - `tests/unit/test_search_*.py`
  - `tests/unit/test_meili_*.py`
  - `tests/unit/test_embedding_encoder.py`
  - `tests/integration/test_search_api.py`

### translation
PDF translation — self-hosted LibreTranslate HTTP client with timeout,
retry, and graceful fallback (returns original text on error).

- **Entry point:** `src/services/translation/client.py` (`LibreTranslateClient`)
- **Key deps:** httpx
- **Tests:**
  - `tests/unit/test_translation.py`
  - `tests/integration/test_translation_versions.py`

### vault
Vault export — group-scoped Markdown/ZIP bundle of document intelligence
(summaries, keywords, metadata) suitable for offline consumption in
Obsidian or similar tools.

- **Entry point:** `src/services/vault/service.py` (`VaultExportService`)
- **Router:** `src/services/api/routers/vault.py`
- **Key deps:** documents, intelligence
- **Tests:** none yet

## How to use

Loaded in a single `read_file` call, this manifest tells an agent which
service owns a given concern without grepping the tree:

```bash
# Before: discover which service handles search
rg "class.*Search" src/services/ --files-with-matches  # 3+ calls, many results

# After: read the manifest
read_file SERVICES.md  # 1 call — find "search" entry, jump to src/services/search/
```

## Notes

- `src/services/api/` is the FastAPI application shell, not a domain service.
  All HTTP endpoints route through it but domain logic lives in the domain
  service directories.
- `src/services/health.py` is a standalone module (not a subdirectory) for the
  shared health-check response type.
- `src/services/pipeline/` is the largest service: 18 Python files covering
  the full ingestion lifecycle (parse → translate → embed → index) plus
  alert matching and intelligence task processing.
- Comments/annotations are handled by the **annotations** service (with
  threaded replies), not a separate `comments` service.
- `src/shared/` provides cross-cutting infrastructure (config, DB helpers,
  logging, metrics, events); it is not listed here as a domain service.
