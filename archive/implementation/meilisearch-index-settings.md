# Meilisearch Index Settings — Decisions

**Scope:** Index name, searchable/filterable/sortable attributes, ranking rules,
`distinctAttribute`, stop words, synonyms, typo tolerance, faceting, displayed attributes.
**Does not cover:** ACL filter construction (security issue #302), indexing pipeline (#303),
multilingual query routing (#304).
**Companion file:** `src/services/search/meili_settings.py`

---

## Index name

`documents`

A single index holds all chunk records. There is no per-language index split
(see multilingual decision below). A shadow index `documents_shadow` is used
during safe reindex/swap operations and is never the live query target.

---

## Attribute naming convention

All attribute paths use snake_case to match the serialized Pydantic field names.
Example: `document_id`, `allowed_group_ids`, `metadata.file_name`, `content_en`.

---

## Searchable attributes

Order determines attribute weight in the `attribute` ranking rule.
Earlier position = higher weight = stronger boost when a query term matches there.

```
title, title_en, title_he          — document title, highest weight
heading, heading_en, heading_he    — section headings
subtitle, description              — structural overview fields
content, content_en, content_he    — chunk body, core match field
summary, summary_en, summary_he    — generated summaries
section_path                       — heading hierarchy (array)
metadata_text                      — catch-all blob (allowlisted metadata)
metadata.file_name                 — searchable file name
metadata.path                      — searchable file/connector path
metadata.url                       — searchable source URL
metadata.author, metadata.owner    — people fields
metadata.tags, metadata.labels, metadata.topics  — classification terms
metadata.project, metadata.workspace, metadata.collection  — org hierarchy
```

**Not searchable:** `allowed_group_ids`, `is_admin_only`, `content_checksum`,
`indexed_at`, `metadata.checksum`, `metadata.version`, `metadata.mime_type`,
`metadata.file_extension`.

Rationale for `metadata.path` and `metadata.url` being searchable:
a user searching "github.com/org/repo" or "/reports/q4" should find matching
documents. They are excluded from `metadata_text` and `displayed_attributes`
so they never appear in snippets or returned results.

---

## Filterable attributes

Must include `allowed_group_ids` and `is_admin_only` — required for the ACL filter.

```
document_id          — fetch all chunks of a document
allowed_group_ids    — ACL filter (applied on every query)
is_admin_only        — admin-restricted documents
chunk_index          — within-document navigation
metadata.source
metadata.document_type
metadata.mime_type
metadata.file_extension
metadata.language
metadata.author
metadata.owner
metadata.tags
metadata.labels
metadata.topics
metadata.project
metadata.workspace
metadata.collection
metadata.created_at
metadata.updated_at
metadata.imported_at
```

**Not filterable:** `metadata.checksum`, `metadata.version` — internal fields,
no user-facing filter use case.

---

## Sortable attributes

```
metadata.created_at
metadata.updated_at
metadata.imported_at
chunk_index          — within-document ordering (secondary sort)
position.page_number — within-document page ordering (secondary sort)
```

---

## `distinctAttribute`

`document_id`

Meilisearch returns at most one chunk per `document_id` (the highest-scoring chunk).
This prevents five chunks from the same document dominating the first result page.

When callers need adjacent chunks (context expansion), they query by
`document_id = X` with a `chunk_index` sort — this is not a search query, it is
a filtered fetch.

---

## Ranking rules

Meilisearch defaults. No custom rules needed at this stage.

```
words → typo → proximity → attribute → sort → exactness
```

The `attribute` rule already boosts title and heading matches over content matches
because of their earlier position in `searchable_attributes`.

---

## Stop words

Stop words prevent common particles from inflating scores. Particularly important
for Hebrew, where common grammatical particles (prepositions, pronouns, conjunctions)
appear in almost every sentence.

### English stop words added

`a, an, the, and, or, of, in, to, for, is, it, on, at, by, with, from, as`

Meilisearch's built-in tokenizer already handles many English stop words.
This list augments rather than replaces built-in behaviour.

### Hebrew stop words added

The following are the highest-frequency particles that carry no discriminating
search value:

```
של (of/belonging to)    עם (with)           את (accusative marker / you f.)
הם (they m.)            הן (they f.)        הוא (he)
היא (she)               אני (I)             אתה (you m.)
כי (because/that)       לא (not/no)         על (on/about)
אל (to/don't)           גם (also)           רק (only)
כל (all/every)          זה (this m.)        זו (this f.)
אנחנו (we)              אבל (but)           כן (yes)
לו (to him)             לה (to her)         אם (if)
כאשר (when)             אשר (which/that)    כך (thus/so)
כבר (already)           עוד (still/more)    כאן (here)
יש (there is)           אין (there is not)  מה (what)
מי (who)                איך (how)           מתי (when)
לפני (before)           אחרי (after)        בין (between)
```

Conservative list — does not include `שם` (there/name — ambiguous) or
`כן` when used as a proper name prefix.

---

## Synonyms

Covers document-type shorthand used in file names and tags.

```
spec  ↔  specification, specifications
prd   ↔  product requirements, requirements document
design  ↔  design doc, design document
notes   ↔  meeting notes, meeting minutes
transcript  ↔  meeting transcript, call transcript, recording transcript
```

---

## Typo tolerance

Meilisearch defaults with the following overrides:

- Typo tolerance **disabled** on `metadata.tags`, `metadata.labels`,
  `metadata.collection`, `allowed_group_ids` — these are exact classification
  strings; a typo produces a wrong filter, not a fuzzy match.
- Default word-length thresholds are kept for all other attributes.

---

## Faceting

Used to populate the filter panel (already built in Phase 08c).
`maxValuesPerFacet: 100` to avoid truncating large tag sets.

Faceted attributes:

```
metadata.document_type
metadata.source
metadata.language
metadata.tags
metadata.labels
metadata.topics
metadata.project
metadata.workspace
metadata.collection
```

Sort facet values by count (most common first).

---

## Displayed attributes

Controls which fields are returned in search results. Excludes security and
internal fields.

**Included:**

```
id, document_id, chunk_index
title, title_en, title_he
heading, heading_en, heading_he
subtitle, description
content, content_en, content_he
summary, summary_en, summary_he
section_path
position
metadata.source, metadata.document_type, metadata.mime_type
metadata.file_name, metadata.file_extension
metadata.language, metadata.author, metadata.owner
metadata.tags, metadata.labels, metadata.topics
metadata.project, metadata.workspace, metadata.collection
metadata.created_at, metadata.updated_at, metadata.imported_at
```

**Excluded (never returned to callers):**

```
allowed_group_ids    — ACL field; never expose
is_admin_only        — internal security flag
content_checksum     — internal dedup field
indexed_at           — internal provenance
metadata.checksum    — internal file hash
metadata.version     — internal versioning
metadata.path        — filesystem/connector path (may reveal internal layout)
metadata.url         — source URL (may be sensitive depending on connector)
metadata_text        — catch-all blob; snippets come from individual content fields
```

---

## Settings application

Settings must be applied **idempotently** at startup. If the index does not exist,
create it and apply settings. If it already exists, update settings without
dropping documents.

The only setting that requires a full reindex if changed is `filterableAttributes`
(Meilisearch rebuilds the filter index). Changing `searchableAttributes` or
`rankingRules` does not drop existing documents.

Settings are versioned as a constant in `meili_settings.py`. When settings change,
increment `SETTINGS_VERSION` so operators can detect a drift between applied and
desired settings.

---

## Acceptance criteria

- [ ] `meili_settings.py` exports `INDEX_NAME`, `SHADOW_INDEX_NAME`, `INDEX_SETTINGS`, `SETTINGS_VERSION`
- [ ] `allowed_group_ids` is in `filterable_attributes`
- [ ] `allowed_group_ids`, `is_admin_only`, `content_checksum`, `indexed_at` are **not** in `displayed_attributes`
- [ ] `metadata.checksum` and `metadata.version` are **not** in `filterable_attributes`
- [ ] `distinct_attribute` is `"document_id"`
- [ ] Hebrew stop words list is non-empty
- [ ] `apply_index_settings(client)` is idempotent — safe to call on every startup
- [ ] Unit test: settings dict contains all required keys, no unknown top-level keys
- [ ] `mypy src --strict` passes
