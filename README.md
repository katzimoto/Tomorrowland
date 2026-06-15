# Tomorrowland

<p align="center">
  <strong>Local-first knowledge intelligence for private document corpora</strong>
  <br>
  Permission-filtered semantic &amp; full-text search · RAG Q&amp;A · Translation · Previews · Alerts · Air-gapped
</p>

<p align="center">
  <a href="#-quick-start"><img src="https://img.shields.io/badge/-quick%20start-0a7cff?style=flat-square" alt="Quick Start"></a>
  <a href="docs/operations/production-compose.md"><img src="https://img.shields.io/badge/-production-6f42c1?style=flat-square" alt="Production"></a>
  <a href="docs/operations/air-gapped-deployment.md"><img src="https://img.shields.io/badge/-air--gapped-22863a?style=flat-square" alt="Air-Gapped"></a>
  <a href="docs/index.md"><img src="https://img.shields.io/badge/-documentation-f6f8fa?style=flat-square" alt="Docs"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/react-19-61dafb?style=flat-square" alt="React 19">
  <img src="https://img.shields.io/badge/version-0.6.0--rc-dc3545?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/license-proprietary-red?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/PRs-welcome-2ea043?style=flat-square" alt="PRs Welcome">
</p>

---

## 📌 At a Glance

| | |
|---|---|
| **What** | Permission-filtered document intelligence platform — search, RAG, translate, preview, alerts |
| **Where it runs** | Your hardware — bare metal, VM, or air-gapped server |
| **Network** | Fully offline capable — no internet required at runtime |
| **AI** | Local LLMs via Ollama (optional) or external providers (OpenAI-compatible) |
| **Scale** | 10x–100K+ documents per source, group-based access control |
| **License** | Proprietary |

---

## 🚀 Quick Start

```bash
cp .env.example .env
docker compose up --build
```

| | URL |
|---|---|
| 🌐 **Frontend** | [localhost:8080](http://localhost:8080) |
| ❤️ **API Health** | [localhost:8000/health](http://localhost:8000/health) |
| 📚 **Full Setup** | [docs/development/local-dev.md](docs/development/local-dev.md) |

For production or air-gapped deployment:

```bash
# Production-style (detached) — see docs/operations/production-compose.md
docker compose up -d

# Air-gapped — see docs/operations/air-gapped-deployment.md
./scripts/tomorrowland-airgap.sh up
```

---

## ✨ Features

Tomorrowland turns a private document corpus into an intelligent, searchable, collaborative workspace.

### 🔎 Hybrid Search
BM25 full-text + semantic vector search with typo tolerance, filters (source, date, tags), and configurable BM25/vector weighting. Powered by **Meilisearch** + **Qdrant**.

### 📄 Document Preview
Type-specific in-browser renderers — PDF, code, images, video, audio, text, and Office docs (via LibreOffice). With annotations, highlights, and version history.

### 🤖 Local RAG Q&A
Permission-filtered chunk retrieval over your documents — answers from your data, not the open web. Runs on **Ollama** with optional streaming, query rewrite, and reranking.

### 🌐 Translation
Bundled **LibreTranslate** for offline translation. Auto-enrichment detects source language and publishes translation jobs at ingest time. Manual translations available on demand.

### 🔔 Intelligent Alerts
Topic subscriptions with ingest-time notifications. Subscribe to subjects (via query) and get alerted when new documents match.

### 🧠 Document Intelligence
Background workers extract summaries, entities, tags, and key points per document — all through local LLMs.

### 🔒 Permission-Filtered Everything
Group-based access control at source granularity. Search, preview, download, and RAG all enforce the same permission model consistently.

### 📦 Fully Air-Gapped
Split Docker images, optional model weight bundles, no external API calls at runtime. Deploy to disconnected networks with a single script.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Users / Clients                           │
├───────────────────────┬─────────────────────────────────────────┤
│                       │                                         │
│  ┌───────────────┐   │   ┌─────────────────────────────────┐   │
│  │    React 19    │   │   │        FastAPI Backend           │   │
│  │   TypeScript   │   │   │  ┌──────────┬────────────────┐  │   │
│  │    SPA + Vite  │   │   │  │  Auth /  │   Search /    │  │   │
│  │               │   │   │  │  Admin   │   Preview /    │  │   │
│  │    Port 8080  │   │   │  │  Routes  │   RAG / Chat   │  │   │
│  └───────┬───────┘   │   │  └────┬─────┴───────┬────────┘  │   │
│          │           │   │       │             │            │   │
└──────────┼───────────┘   └───────┼─────────────┼────────────┘   │
           │                       │             │                 │
           │               ┌───────┴──────┬──────┴────────┐        │
           │               │   Postgres   │   Pipeline    │        │
           │               │  (metadata,  │    Workers    │        │
           │               │   users,     │  (parse →      │        │
           │               │   perms)     │   translate →  │        │
           │               └──────────────┘   embed →      │        │
           │                               └───────┬───────┘        │
           │                                       │                │
     ┌─────┴───────────────────────────────────────┴──────────┐     │
     │                      Data Stores                        │     │
     │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │     │
     │  │  Qdrant  │  │Meilisearch│  │ RabbitMQ │  │ Redis  │ │     │
     │  │ (vectors)│  │ (BM25 FT) │  │ (pipeline)│  │ (cache)│ │     │
     │  └──────────┘  └──────────┘  └──────────┘  └────────┘ │     │
     └────────────────────────────────────────────────────────┘     │
                                                                   │
  ┌─────────────────────────────────────────────────────────────┐  │
  │               Optional / Plug-in Services                    │  │
  │  ┌──────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐ │  │
  │  │  Ollama  │  │LibreTranslate│  │  Redpanda │  │  MCP    │ │  │
  │  │(LLM/emb) │  │(translation) │  │  (Kafka)  │  │ Adapter │ │  │
  │  └──────────┘  └──────────────┘  └──────────┘  └─────────┘ │  │
  └─────────────────────────────────────────────────────────────┘  │
```

### Pipeline Flow

```
Document Upload → Parse → Detect Language → Translate → Chunk →
Embed (vector) → Index (BM25) → Intelligence (summarize/extract/tag)
```

---

## 📦 Services

| Service | Role | Required |
|---------|------|----------|
| **FastAPI Backend** | Auth, admin, search, preview, RAG, documents, annotations API | ✅ |
| **React Frontend** | Modern SPA with Vite + React 19 + TypeScript | ✅ |
| **PostgreSQL** | Application metadata, users, groups, permissions, config | ✅ |
| **Meilisearch** | BM25 full-text search with typo tolerance | ✅ |
| **Qdrant** | Vector search for semantic & hybrid retrieval | ✅ |
| **RabbitMQ** | Pipeline stage message bus | ✅ |
| **Redis** | Caching (config, rate limits, sessions) | ✅ |
| **Ollama** | Local LLM for RAG, summaries, entities, tags, embeddings | optional |
| **LibreTranslate** | Bundled offline document translation | optional |
| **Redpanda (Kafka)** | NiFi event ingestion bus | optional |
| **MCP Adapter** | Hermes client tool connectivity | optional |

---

## 🔌 Connectors

| Source | Method | Status |
|--------|--------|--------|
| **Folder** | Host-mounted paths | ✅ Available |
| **SMB/CIFS** | Host-mounted, read-only | ✅ Available |
| **Confluence** | Server / Data Center API | ✅ Available |
| **Jira** | Server / Data Center API | ✅ Available |
| **NiFi** | Kafka event ingestion | ✅ Available |
| **Email (IMAP)** | Ingest from mailboxes | 🔜 Planned |

---

## 🛠️ Development

### Backend

| Tool | Purpose |
|------|---------|
| Python 3.11+ | Runtime |
| FastAPI + Uvicorn | ASGI web framework |
| SQLAlchemy + Alembic | Database ORM & migrations |
| [uv](https://docs.astral.sh/uv/) | Package manager |
| pytest | Testing |

```bash
# Quality gate (run before commit)
uv run ruff check --fix src/ tests/ migrations/
uv run ruff format src/ tests/ migrations/
uv run mypy src --strict
uv run pytest

# Local LLM dev mode (optional — for CPU-only / limited-RAM machines)
# See docs/context/local-llm-dev.md
export FEATURE_LOCAL_LLM_DEV=true
```

### Frontend

| Tool | Purpose |
|------|---------|
| React 19 + TypeScript | UI framework |
| Vite | Build tool |
| TanStack Query v5 | Server state |
| Vitest + Playwright | Testing |

```bash
cd frontend
npm run lint
npx vitest run
```

📖 [Dev setup guide](docs/development/local-dev.md) · [Testing guide](docs/development/testing.md)

---

## 📚 Documentation

Full documentation at the [MkDocs wiki](docs/index.md):

| Section | For |
|---------|-----|
| [Getting Started](docs/development/local-dev.md) | Newcomers — setup, architecture, logical spec |
| [Deploy & Operate](docs/operations/production-compose.md) | Operators — deployment, air-gapped, pipeline, monitoring |
| [Develop](docs/context/README.md) | Developers — backend, search, extraction, frontend, ACL, local LLM |
| [Design & Specs](docs/design/README.md) | Architects — feature specs, permissions, logging, metrics |
| [API Reference](docs/api/search.md) | Developers — auto-generated from docstrings |
| [Agent Guide](docs/agents/README.md) | AI coding agents — workflow, templates, documentation policy |

🔗 [Open wiki](docs/index.md) · [CHANGELOG](CHANGELOG.md) · [Roadmap](docs/roadmap.md)

---

## 🔒 Security & Privacy

- **JWT authentication** with local accounts and optional LDAP integration
- **Group-based ACL** at source granularity — enforced on every search, preview, download, and RAG request
- **Air-gapped by design** — no external API calls, no telemetry, no phone-home at runtime
- **SSRF protection** on all external provider URLs
- **No secrets in artifacts** — credentials stay in `.env`, never in release bundles or source control

---

## 🤝 Contributing

This is an internal proprietary project. Pull requests from team members are welcome. Please:

1. Open an issue first for non-trivial changes
2. Follow the [coding behavior guide](docs/agents/coding-behavior.md)
3. Run the full quality gate locally before pushing
4. See [the agent guide](docs/agents/README.md) for the full workflow

---

## 📄 License

Proprietary. All rights reserved.
