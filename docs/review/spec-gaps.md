# Spec Gaps And Decision Log

These items must be resolved before implementation reaches the affected phase.

## Blockers Before Phase 01

- **Document persistence model:** the spec references documents, `group_id`,
  `translation_quality`, indexes, and delete cascade, but does not define a
  primary `documents` table.
- **Document identity:** Kafka events define `doc_id` as a UUID, while Atlassian
  mappings use deterministic string identifiers like `jira:{issue_key}`.
- **Group ownership:** `group_id` appears on document events and index payloads,
  but source permissions are modeled as many-to-many source/group mappings.
- **NiFi ownership:** `documents.raw` is both the ingestion output and the
  `worker-fast` input, but NiFi is described as a source consumed by ingestion
  from the same topic.

## Blockers Before Phase 03

- **Chunk text source:** RAG citations require chunk text. The spec should state
  whether chunk text is stored in Qdrant payloads, Postgres, or both.
- **Delete source of truth:** delete cascade references indexed data and
  auxiliary tables, but needs a transaction/consistency owner for document rows.
- **Translation state:** `translation_quality` appears in indexed documents, but
  the persistence table and valid transitions need to be explicit.

## Blockers Before Phase 05

- **Annotation retention:** delete cascade says annotations are marked
  `doc_deleted: true`, but the annotation schema does not include that column.
- **Preview positions:** annotation `position` is preview-mode dependent; define
  minimum shapes for HTML, PDF/image, table, and text previews.

## Blockers Before Phase 08

- **Atlassian permissions:** manual group mapping is mentioned, but page/project
  permission synchronization is out of scope or undefined.
- **Atlassian URL validation:** `*.atlassian.net` rejection should define exact
  hostname matching and whether redirects are followed.

## Default Decisions For Planning

- Keep `spec.md` and `spec-v4.pdf` unchanged as source references.
- Track resolved decisions by updating this file and the affected phase plan.
- Do not implement a phase whose blockers are still open.
