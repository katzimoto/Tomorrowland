# Design & Specs

Feature specifications, design decisions, and architectural specs for Tomorrowland.

## Documents

Designs for document viewing, chat, comments, and AI-powered surfaces.

- [AI Surfaces](../operators/ai-surfaces.md) — RAG, search, intelligence, and AI model configuration
- [Document Viewer](document-viewer-design.md) — preview components and MIME dispatch
- [Viewer Guardrails](document-viewer-implementation-guardrails.md) — implementation constraints for viewer components
- [Document Chat](document-chat-design.md) — streaming RAG chat with citations
- [Document Comments](document-comments-spec.md) — threaded comments on documents

## Platform

Core platform architecture and data model specs.

- [Sources & Permissions](sources-permissions-model.md) — document access control model
- [Translation Versions](translation-versions-spec.md) — translation versioning and enrichment
- [SQLModel Bounded Models](../architecture/sqlmodel-bounded-models.md) — SQLModel type boundaries

## Observability

Logging, metrics, and monitoring system design.

- [Logging System](logging-system-spec.md) — structured JSON logs, redaction, and event taxonomy
- [Metrics & Monitoring](metrics-monitoring-spec.md) — Prometheus metrics, dashboards, and alerting

## UI & UX

User interface and user experience specifications.

- [User UI](user-ui-spec.md) — interface patterns and component library
- [Logo Options](logo-options.md) — branding and logo explorations
