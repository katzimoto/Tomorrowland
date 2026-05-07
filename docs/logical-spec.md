# Local Semantic Search Engine Logical Spec

This document separates product and system behavior from implementation sequencing.
The canonical references remain `spec.md` and `spec-v4.pdf`.

## Purpose

Neverland is a local-first knowledge intelligence system for private document
corpora. It provides permission-filtered semantic and full-text search, local
RAG Q&A, translation, previews, annotations, alerts, expertise mapping, related
document surfacing, and admin-configurable operation.

## Actors

- Users authenticate through local credentials, LDAP, or both.
- Admins manage users, groups, ingestion sources, permissions, system config,
  DLQ retries, and audit views.
- Background workers ingest, index, enrich, translate, summarize, tag, and
  match alerts.

## Access Model

- Every document access path is filtered by the user's group memberships.
- Admin-only operations are enforced by backend router guards.
- Shared annotations are visible to users with document access.
- Private annotations are visible only to their owner.
- Feature-flagged capabilities return hidden or disabled behavior when off.

## Core Capabilities

- Ingest documents from folders, NiFi, Confluence Server/Data Center, and Jira
  Server/Data Center.
- Extract text, OCR where needed, translate to English, chunk content, embed
  chunks, and index both BM25 and vector search data.
- Search with configurable BM25/vector weights and source/date/tag filters.
- Preview files through type-specific renderers.
- Request high-quality translation manually or through automatic view-count
  enrichment.
- Ask RAG questions using permission-filtered chunks and local Ollama models.
- Generate document summaries, entities, and tags as best-effort intelligence.
- Create topic subscriptions and generate alert notifications at ingest time.
- Track user activity for audit and expertise mapping.
- Retain operational observability through logs, metrics, DLQ, and health checks.

## Domain Concepts

- **User:** authenticated identity with admin status, auth source, and groups.
- **Group:** permission boundary used for search, preview, download, and RAG.
- **Ingestion Source:** configured origin for files or external systems.
- **Document:** searchable unit created by ingestion and linked to source access.
- **Chunk:** vector-searchable section of a document.
- **Summary, Entity, Tag:** generated intelligence attached to a document.
- **Annotation:** user-created note or highlight on a document preview.
- **Subscription:** user-owned topic query used for proactive alerts.
- **Notification:** unread/read alert generated from subscription matching.
- **System Config:** runtime admin-editable feature flags and tunables.
- **DLQ Record:** failed event retained for admin inspection and retry.

## Public Interfaces

- REST APIs expose auth, search, Q&A, preview, download, annotations, activity,
  subscriptions, notifications, expertise, related documents, and admin panels.
- Kafka topics carry raw document events, enrichment requests, intelligence
  requests, and dead-lettered events.
- Elasticsearch stores document-level full-text search data.
- Qdrant stores chunk-level vectors and payloads.
- Postgres stores users, permissions, sources, activity, generated intelligence,
  subscriptions, notifications, config, and ingestion state.

## Non-Functional Requirements

- Fully air-gapped in v1: no external LLM, translation, or SaaS API calls.
- Target document capacity is 500K+ documents.
- Search latency target is below 300 ms.
- Q&A latency target is below 10 seconds.
- Feature flag updates propagate within 60 seconds.
- Logs are structured JSON and include correlation IDs.
- Worker retries use bounded exponential backoff and DLQ where specified.
- Intelligence failures are best-effort and must not block ingestion.
