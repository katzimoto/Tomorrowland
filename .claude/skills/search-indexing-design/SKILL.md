---
name: search-indexing-design
description: Use for Tomorrowland search, indexing, metadata search, translated document variants, Qdrant/vector retrieval, reindexing, and search quality design.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: search-agents
---

# Search Indexing Design

## Domain stance

Tomorrowland indexes documents, not issues. Design indexes around document discovery, metadata filtering, translated content, previews, permissions, and retrieval quality.

## Search surfaces

Consider these fields when planning search/indexing work:

- Document id and workspace id.
- Title, filename, extension, MIME type, source, and path display label.
- Extracted original text.
- Translated text variants and language codes.
- Metadata fields and normalized metadata facets.
- Permissions/visibility attributes.
- Preview/snippet fields.
- Timestamps: created, modified, ingested, indexed, translated.
- Embedding/vector references where enabled.

## Design checklist

Before implementation, answer:

1. Which user query or filter is being improved?
2. Which index or collection changes?
3. How are metadata and translated variants represented?
4. How are permissions enforced at query time?
5. What happens during reindex or migration?
6. What is the rollback or stale-index behavior?
7. How will quality be verified?

## Guardrails

- Do not leak documents across permission boundaries.
- Do not index private source paths as user-visible labels unless intended.
- Do not assume original and translated text are interchangeable.
- Do not break existing filters while adding fields.
- Do not introduce a new search engine abstraction unless required.

## Verification ideas

- Query original-language text.
- Query translated text.
- Filter by metadata.
- Confirm unauthorized documents are excluded.
- Reindex a small fixture set.
- Check empty and partial-index states.
