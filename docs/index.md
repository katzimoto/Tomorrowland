# Tomorrowland

**Local-first knowledge intelligence system for private document corpora.**

Tomorrowland provides permission-filtered semantic and full-text search, local RAG Q&A, translation, document previews, annotations, alerts, expertise mapping, and admin-configurable operation — all running fully air-gapped on your own infrastructure.

---

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | <http://localhost:8080> |
| API Health | <http://localhost:8000/health> |

[:octicons-arrow-right-24: Full setup guide](development/local-dev.md)

---

## I want to…

### Run Tomorrowland

→ [Getting Started](development/local-dev.md) — set up a dev environment  
→ [Production Compose](operations/production-compose.md) — deploy and run in production  
→ [Air-Gapped Deployment](operations/air-gapped-deployment.md) — offline installation with split image parts  

### Understand the system

→ [Architecture Overview](architecture/overview.md) — runtime components and data model  
→ [Logical Spec](logical-spec.md) — product behavior reference  
→ [Pipeline Workers](operations/pipeline-workers.md) — how documents flow through the system  

### Write code

→ [Local Development](development/local-dev.md) — repository setup and runtime orientation  
→ [Backend API](context/backend-api.md) — FastAPI routes, auth guards, persistence  
→ [Search](context/search.md) — Meilisearch, Qdrant, hybrid search  
→ [Frontend](context/frontend.md) — React/Vite UI work and testing  
→ [Testing Guide](development/testing.md) — targeted backend and frontend checks  

### Understand a feature design

→ [Sources & Permissions](design/sources-permissions-model.md) — document access control model  
→ [Document Viewer](design/document-viewer-design.md) — preview components and MIME dispatch  
→ [Document Chat](design/document-chat-design.md) — streaming RAG chat with citations  
→ [Logging System](design/logging-system-spec.md) — structured JSON logs and redaction rules  
→ [Metrics & Monitoring](design/metrics-monitoring-spec.md) — Prometheus metrics and dashboards  

### Manage AI models and surfaces

→ [Model Providers](operations/model-providers.md) — configure local and external LLM providers  
→ [AI Surfaces](operators/ai-surfaces.md) — RAG, search, intelligence, and permissioned APIs  
→ [MCP Adapter](operations/mcp-adapter.md) — connect Hermes clients to researcher tools  

### Work with AI agents (Codex, Claude, Copilot)

→ [Agent Guide](agents/README.md) — issue-first workflow for coding agents  
→ [Coding Behavior](agents/coding-behavior.md) — execution discipline and guardrails  
→ [Documenting Features](agents/documenting-features.md) — what docs to update per change type  
→ [Token Efficiency](agents/token-efficiency.md) — context-loading rules  

### Understand project decisions and roadmap

→ [Decisions Log](memory/decisions.md) — key architectural choices and their rationale  
→ [Glossary](memory/glossary.md) — terminology reference  
→ [History & Roadmap](roadmap.md) — release history, planned work, and commit log  

---

## Architecture at a Glance

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
│  React   │  │ FastAPI  │  │ Pipeline │  │ Intelligence │
│ Frontend │──│ Backend  │──│ Workers  │──│   Workers    │
└──────────┘  └──────────┘  └──────────┘  └──────────────┘
                    │              │              │
              ┌─────┴──────┬───────┴──────┬───────────────┐
              │  Postgres  │  Meilisearch │    Qdrant     │
              │  (metadata)│  (full-text) │   (vectors)   │
              └────────────┴──────────────┴───────────────┘
```

[:octicons-arrow-right-24: Full architecture overview](architecture/overview.md)

---

## Core Capabilities

| Capability | Description |
|-----------|-------------|
| **Ingest** | Documents from folders, NiFi, Confluence, and Jira |
| **Search** | Configurable BM25/vector hybrid search with source, date, and tag filters |
| **Preview** | Type-specific renderers for documents in-browser |
| **RAG Q&A** | Permission-filtered chunk retrieval with local Ollama models |
| **Translate** | High-quality translation with manual request or auto-enrichment |
| **Annotations** | User-created notes and highlights on document previews |
| **Alerts** | Topic subscriptions with ingest-time notifications |
| **Intelligence** | Summaries, entities, and tags generated for every document |

---

## Air-Gapped Ready

Tomorrowland ships fully air-gapped: no external LLM, translation, or SaaS API calls required. Optional Ollama model bundles for offline Q&A and intelligence.

[:octicons-arrow-right-24: Air-gapped deployment guide](operations/air-gapped-deployment.md)
