# Architecture Overview

Tomorrowland is a local-first knowledge intelligence system packaged as a Docker
Compose application for connected and air-gapped environments.

## Runtime components

- FastAPI backend for auth, admin operations, document APIs, search, preview,
  comments, annotations, subscriptions, readiness, and orchestration endpoints.
- React frontend built with TypeScript and Vite.
- PostgreSQL for application metadata and permissions.
- Elasticsearch for keyword search.
- Qdrant for vector search.
- Kafka-compatible event plumbing for NiFi-produced events where configured.
- LibreTranslate for bundled offline translation language packs.
- Optional Ollama runtime and model bundle for local Q&A/RAG and intelligence.

## Data-safety model

Persistent product data lives in named Docker volumes and operator-controlled
host mounts. Air-gapped upgrades preserve `.env` and volumes, load images from
local artifacts, run migrations through the documented path, and never require
volume deletion.

## Release artifact model

- Platform archive: small `tomorrowland-release-<version>.tar.gz` with Compose,
  env templates, scripts, docs, manifests, and checksums.
- Image parts: required split `tomorrowland-images-<version>.tar.part-*` files
  loaded by the air-gapped wrapper without manual concatenation.
- Optional model bundle: Ollama model weights for offline Q&A/RAG/local
  intelligence. Platform startup does not require model weights.
