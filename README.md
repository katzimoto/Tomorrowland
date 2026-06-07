<h1 align="center">Tomorrowland</h1>

<p align="center">
  <strong>Local-first knowledge intelligence for private document corpora</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/react-19-61dafb" alt="React 19">
  <img src="https://img.shields.io/badge/license-proprietary-red" alt="License">
</p>

---

## ✨ What is Tomorrowland?

Tomorrowland indexes your files and enterprise sources into a **private, permission-filtered search workspace** with previews, translation, collaboration, and optional local LLM-powered intelligence. It runs fully air-gapped — no internet required at runtime.

| 🚀 **Search** | 📄 **Preview** | 🤖 **RAG Q&A** | 🌐 **Translate** |
|---|---|---|---|
| Hybrid BM25/vector search with source, date & tag filters | Type-specific renderers for documents in-browser | Permission-filtered chunk retrieval with local models | Auto-enrichment & manual translation via LibreTranslate |

| 🔒 **Permissions** | 🔔 **Alerts** | 🧠 **Intelligence** | 📦 **Air-Gapped** |
|---|---|---|---|
| Group-based access control at source granularity | Topic subscriptions with ingest-time notifications | Summaries, entities & tags generated per document | Offline deployment with split image parts & optional model bundle |

---

## 🚀 Quick Start

```bash
cp .env.example .env
docker compose up --build
```

| | URL |
|---|---|
| Frontend | [localhost:8080](http://localhost:8080) |
| API Health | [localhost:8000/health](http://localhost:8000/health) |

[:books: Full setup guide](docs/development/local-dev.md) · [:package: Production deployment](docs/operations/production-compose.md) · [:lock: Air-gapped install](docs/operations/air-gapped-deployment.md)

---

## 🏗️ Architecture

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

| Service | Role |
|---|---|
| **FastAPI** | Auth, admin, search, preview, RAG, documents API |
| **React + TypeScript** | Modern SPA frontend with Vite |
| **PostgreSQL** | Application metadata, users, groups, permissions |
| **Meilisearch** | BM25 full-text search with typo tolerance |
| **Qdrant** | Vector search for semantic & hybrid retrieval |
| **RabbitMQ** | Pipeline stage message bus (parse → translate → embed → index) |
| **LibreTranslate** | Bundled offline translation |
| **Kafka** (Redpanda) | NiFi event ingestion bus |
| **Ollama** (optional) | Local LLM for RAG, summaries, entities, tags |

[:books: Full architecture](docs/architecture/overview.md)

---

## 📦 Air-Gapped Deployment

Tomorrowland ships as a small platform archive plus split Docker image parts — no runtime internet, no SaaS dependencies, no external API calls.

```bash
./scripts/tomorrowland-airgap.sh validate --load-images
./scripts/tomorrowland-airgap.sh up
```

| Required | Optional |
|---|---|
| `tomorrowland-release-<version>.tar.gz` | `tomorrowland-ollama-bundle-<model>-<version>.tar.gz` |
| `tomorrowland-images-<version>.tar.part-*` | _(local AI model weights — not needed for platform startup)_ |

[:books: Air-gapped deployment guide](docs/operations/air-gapped-deployment.md) · [:book: README-airgap](README-airgap.md)

---

## ⬆️ Upgrade

Upgrades preserve `.env` and persistent Docker volumes:

```bash
./scripts/tomorrowland-airgap.sh upgrade \
  --artifact-dir ../tomorrowland-release-<version>
```

> **Never use `docker compose down -v` for upgrades.** The `-v` flag deletes persistent product data volumes.

[:arrow_up: Full upgrade guide](docs/operations/air-gapped-upgrade.md)

---

## 📋 Release Artifacts

| Term | Meaning |
|---|---|
| Platform archive | `tomorrowland-release-<version>.tar.gz` — Compose files, env templates, docs, scripts, manifests, checksums |
| Image parts | `tomorrowland-images-<version>.tar.part-*` — split Docker images, loaded by the wrapper automatically |
| Local AI models | `tomorrowland-ollama-bundle-<model>-<version>.tar.gz` — optional Ollama model weights for offline Q&A/RAG |
| Legacy names | Earlier `neverland-*` release asset names may appear in historical notes only. `tomorrowland-*` is canonical for all operator-facing examples. |

---

## 🔌 Connectors

| Connector | Status |
|---|---|
| Folder (host-mounted paths) | ✅ Available |
| SMB/CIFS (host-mounted, read-only) | ✅ Available |
| Confluence Server/Data Center | ✅ Available |
| Jira Server/Data Center | ✅ Available |
| NiFi (Kafka event ingestion) | ✅ Available |

> Some connector hardening remains intentionally optional or deferred, including native NTFS ACL sync and optional Atlassian permission hardening.

---

## 🛠️ Development

| | |
|---|---|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Alembic |
| **Frontend** | React 19, TypeScript, Vite |
| **Package manager** | [uv](https://docs.astral.sh/uv/) |
| **Testing** | pytest (90% coverage floor), Vitest, Playwright |

```bash
# Backend
uv run ruff check --fix src/ tests/ migrations/
uv run mypy src --strict
uv run pytest

# Frontend
cd frontend && npm run lint && npx vitest run
```

[:books: Dev setup](docs/development/local-dev.md) · [:test_tube: Testing guide](docs/development/testing.md)

---

## 📚 Documentation

Full documentation at the [MkDocs wiki](docs/index.md):

| Section | For |
|---|---|
| [Getting Started](docs/development/local-dev.md) | Newcomers — setup, architecture, logical spec |
| [Deploy & Operate](docs/operations/production-compose.md) | Operators — deployment, air-gapped, pipeline, monitoring |
| [Develop](docs/context/README.md) | Developers — backend, search, extraction, frontend, ACL |
| [Design & Specs](docs/design/README.md) | Architects — feature specs, permissions, logging, metrics |
| [API Reference](docs/api/search.md) | Developers — auto-generated from docstrings |
| [Agent Guide](docs/agents/README.md) | AI coding agents — workflow, templates, documentation policy |

[:globe_with_meridians: Open wiki](docs/index.md) · [:memo: CHANGELOG](CHANGELOG.md) · [:rocket: Roadmap & History](docs/roadmap.md)

---

## 🔒 Security

- JWT-based authentication with local accounts and LDAP integration
- Group-based document access control at source granularity
- Air-gapped mode: no external API calls at runtime
- Secrets never stored in release artifacts, docs, or source control
- SSRF protection on external provider URLs

---

## 📄 License

Proprietary. All rights reserved.
