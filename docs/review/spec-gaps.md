# Spec Gaps And Decision Log

These items must be resolved before implementation reaches the affected phase.

## Blockers Before Phase 01

- **Document persistence model:** the spec references documents, `group_id`,
  `translation_quality`, indexes, and delete cascade, but does not define a
  primary `documents` table.
  - **Resolved for Phase 01:** add canonical `documents` table with UUID `id`,
    `source_id`, `external_id`, metadata, language, status, and translation
    fields. Later indexes derive from this table.
- **Document identity:** Kafka events define `doc_id` as a UUID, while Atlassian
  mappings use deterministic string identifiers like `jira:{issue_key}`.
  - **Resolved for Phase 01:** `doc_id` is always the internal UUID. Stable
    source keys are stored as `documents.external_id`, unique per source.
- **Group ownership:** `group_id` appears on document events and index payloads,
  but source permissions are modeled as many-to-many source/group mappings.
  - **Resolved for Phase 01:** access is source-grant based through
    `source_permissions`. Documents do not have a single `group_id`; later
    index payloads use allowed groups derived from their source.
- **NiFi ownership:** `documents.raw` is both the ingestion output and the
  `worker-fast` input, but NiFi is described as a source consumed by ingestion
  from the same topic.
  - **Resolved for Phase 01:** NiFi may publish normalized `documents.raw`
    events directly. Ingestion publishes the same event type for folder and
    Atlassian sources.
  - **Updated for Issue #65:** release support uses a Tomorrowland-owned Kafka
    envelope rather than raw NiFi FlowFiles. The event must identify an enabled
    `nifi` ingestion source by `source_id` or `source_key`, include
    `external_id`, `title` or `filename`, `mime_type`, and a supported payload,
    and is normalized into `documents` before the standard pipeline runs.
    Kafka offsets are committed only after successful pipeline processing or
    successful DLQ routing. Event-level DLQ rows may have no document when the
    event cannot be tied to a valid source/document.

## Blockers Before Phase 03

- **Chunk text source:** RAG citations require chunk text. The spec should state
  whether chunk text is stored in Qdrant payloads, Postgres, or both.
- **Delete source of truth:** delete cascade references indexed data and
  auxiliary tables, but needs a transaction/consistency owner for document rows.
- **Translation state:** `translation_quality` appears in indexed documents, but
  the persistence table and valid transitions need to be explicit.

## Blockers Before Phase 05

- **Preview content shape:** the spec does not define whether preview returns raw
  text, truncated snippet, or rendered HTML.
  - **Resolved for Phase 05a:** preview returns a truncated text snippet
    (first 2000 chars) with MIME-type-aware formatting. A `?full=true` query
    parameter may be added in a future phase for full raw content.
- **View tracking granularity:** the spec mentions view counts but does not
  specify per-user vs global counting or who can see history.
  - **Resolved for Phase 05a:** track per-user views in `document_views` table.
    Users see their own view history via `GET /me/activity`. Admins see global
    activity via `GET /admin/activity` (already implemented in Phase 04).
- **Auto-enrich trigger:** the spec mentions an auto-enrich threshold but does
  not define the mechanism.
  - **Resolved for Phase 05b:** when `document_views` count for a document
    exceeds `system_config.auto_enrich.threshold`, the document is queued for
    slow-worker high-quality translation. This fires exactly once per document.

## Blockers Before Phase 07

- **Annotation retention:** delete cascade says annotations are marked
  `doc_deleted: true`, but the annotation schema does not include that column.
- **Preview positions:** annotation `position` is preview-mode dependent; define
  minimum shapes for HTML, PDF/image, table, and text previews.

## Blockers Before Phase 09

- **Atlassian permissions:** resolved for the implemented Confluence/Jira
  Server/Data Center connectors by using Tomorrowland's source-grant access model.
  Page/project permission synchronization remains an optional hardening feature,
  not a blocker for the shipped polling connectors.
- **Atlassian URL validation:** resolved for the implemented connector baseline:
  reject `atlassian.net` and any subdomain ending in `.atlassian.net`; accept
  non-cloud `http(s)` Server/Data Center base URLs. Redirect-host allowlisting is
  still a future hardening decision only if operators require it.

## Default Decisions For Planning

- Keep `spec.md` and `spec-v4.pdf` unchanged as source references.
- Track resolved decisions by updating this file and the affected phase plan.
- Do not implement a phase whose blockers are still open.
