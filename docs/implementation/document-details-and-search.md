# Document Details & Advanced Search — Implementation Plan
## Issues #483–#489

**Feature branch:** `feature/document-details-and-search`  
All sub-PRs target the feature branch. Only the final integration PR targets `main`.

---

## Track Overview

Seven issues forming a coherent document details + discovery track:

| Issue | Title | Layer | Depends on |
|-------|-------|-------|------------|
| #485 | Rendered Markdown preview | Presentation | — |
| #486 | User-managed private/public tags | Foundation | — |
| #487 | Unify comments into annotations | Foundation | — |
| #488 | Document relationship structure | Foundation | — |
| #483 | Expand shown document details | Presentation | #486, #488 (enriches; not hard-blocked) |
| #484 | Advanced search with field-scoped filters | Discovery | #486 (enriches; not hard-blocked) |
| #489 | Query from document detail values | Discovery | #483 + #484 |

**Recommended merge order within feature branch:**

```
#488 → #486 → #487 → #485 → #483 → #484 → #489 → integration PR → main
```

Parallel-safe for first batch: `#485`, `#486`, `#487`, `#488`.

**Shared-file conflict:** `src/services/api/schemas.py` is touched by #483 and #484.
Assign #483 first; #484 agent rebases before editing schemas.

---

## Issue Plans

---

### #485 — Add rendered preview for Markdown files

**Goal:** Add a `MarkdownPreview` renderer so `.md` / Markdown MIME files render as formatted HTML with a Raw/Rendered toggle.

**Assumptions:**
- No Markdown renderer exists in `frontend/src/features/documents/renderers/`
- `marked` + `dompurify` available or installable
- `PreviewPane.tsx` MIME-dispatch is the integration point

**Out of scope:** Remote image proxying, in-document find in rendered mode.

**Affected files:**
- `frontend/src/features/documents/renderers/MarkdownPreview.tsx` — new renderer
- `frontend/src/features/documents/renderers/MarkdownPreview.test.tsx` — new tests
- `frontend/src/features/documents/PreviewPane.tsx` — add Markdown MIME dispatch branch
- `frontend/src/features/documents/PreviewPane.test.tsx` — add MIME routing test
- `frontend/package.json` — add `marked` + `dompurify` if not present

**Approach:**
1. Install deps: `npm install marked dompurify @types/dompurify` (check first with `rg '"marked"' frontend/package.json`).
2. Create `MarkdownPreview.tsx`: `mode: "rendered" | "raw"` local state. In rendered mode: `DOMPurify.sanitize(marked.parse(text))` as `dangerouslySetInnerHTML`. Config: `FORBID_TAGS: ["script","style"]`. Post-process external links: `target="_blank" rel="noopener noreferrer"`, strip `javascript:` hrefs. In raw mode: delegate to `<TextPreview>`.
3. Wire into `PreviewPane.tsx`: add a Markdown MIME set (`text/markdown`, `text/x-markdown`, `application/markdown`) and an extension fallback for `text/plain` when `preview.title` ends in `.md`/`.markdown`/`.mdown`. Return `<MarkdownPreview text={text ?? ""} />`.
4. Tests: snapshot rendered mode, snapshot raw mode toggle, assert `<script>` is stripped, assert MIME routing.

**Verification:**
```bash
npm run typecheck
npx vitest run src/features/documents/renderers/MarkdownPreview.test.tsx
npx vitest run src/features/documents/PreviewPane.test.tsx
```

**Risks:**
- `marked` v5+ changed to async API — use sync `marked.parse()` or pin to v4.
- `DOMPurify` requires a DOM — use jsdom (already in test setup).

**Open questions:**
- Remote images: recommend blocking by default (strip `img` tags from sanitized output).

---

### #486 — Allow users to add and save private/public document tags

**Goal:** Persist user-created document tags (private or public) in a new `user_document_tags` table, expose via API, render tag UI in the details panel.

**Assumptions:**
- No user tag table exists; `DocumentRow.metadata` holds system auto-tags only.
- `InsightPane.tsx` calls `getTags()` for system tags — user tags need a separate or merged endpoint.

**Out of scope:** Tag autocomplete, bulk tag operations, tag-based search (covered by #484).

**Affected files:**
- `migrations/versions/<hash>_user_document_tags.py` — new migration
- `src/services/documents/models.py` — add `UserDocumentTag` model
- `src/services/documents/repository.py` — add tag CRUD methods
- `src/services/api/routers/documents.py` — add GET/POST/DELETE `/documents/{doc_id}/user-tags`
- `tests/unit/test_user_document_tags.py` — new
- `tests/integration/test_user_tags_api.py` — new
- `frontend/src/api/documents.ts` — add `listUserTags`, `addUserTag`, `deleteUserTag`
- `frontend/src/features/documents/UserTagEditor.tsx` — new tag chip + input + visibility toggle
- `frontend/src/features/documents/UserTagEditor.test.tsx` — new
- `frontend/src/features/documents/InsightPane.tsx` — render `<UserTagEditor>` in details section

**Approach:**
1. Migration: create `user_document_tags (id UUID PK, document_id UUID FK→documents, user_id UUID FK→users, tag VARCHAR(100) NOT NULL, is_private BOOLEAN DEFAULT TRUE, created_at TIMESTAMP)`. Index on `(document_id, user_id)` and `(document_id, is_private)`.
2. Repository: `list_tags(doc_id, viewer_user_id)` returns own private tags + all public tags. `create_tag(doc_id, user_id, tag, is_private)`. `delete_tag(tag_id, user_id, is_admin)` enforces ownership.
3. Router: all endpoints behind `assert_doc_access`. POST validates tag ≤100 chars, max 50 per user per document.
4. `UserTagEditor`: chip list of existing tags, inline input, radio Private/Public, delete button on own tags only.
5. `InsightPane` / `DetailsTab`: add "My Tags" section rendering `<UserTagEditor docId={docId} />`.

**Verification:**
```bash
ruff check --fix src/ && mypy src --strict
pytest tests/unit/test_user_document_tags.py -q
pytest tests/integration/test_user_tags_api.py -q
npm run typecheck && npx vitest run src/features/documents/UserTagEditor.test.tsx
```

**Risks:**
- Public tag visibility must be gated on `assert_doc_access` — never expose tag existence for inaccessible documents.

---

### #487 — Unify comments into the annotations feature

**Goal:** Migrate `document_comments` into document-level annotations (null `position`), add annotation replies, retire the separate comments API and UI.

**Assumptions:**
- `Annotation.position` is nullable (null = document-level) — confirmed in `annotations/models.py`.
- `DocumentComment` has soft-delete fields (`deleted_at`, `deleted_by_id`) — must be preserved.
- Both features exist in `InsightPane.tsx` as separate tabs.

**Out of scope:** Rich text, @-mentions, resolution/status workflow.

**Affected files:**
- `migrations/versions/<hash>_unify_comments_annotations.py` — migrate + add replies table
- `src/services/annotations/models.py` — add `AnnotationReply`; add `reply_count` to list response
- `src/services/annotations/repository.py` — add reply CRUD; update list to include reply count
- `src/services/api/routers/annotations.py` — add `POST /annotations/{id}/replies`, `DELETE /annotation-replies/{id}`
- `src/services/api/routers/comments.py` — return HTTP 410 Gone with migration notice (do not delete file this cycle)
- `tests/unit/test_annotations_unified.py` — new
- `tests/integration/test_annotations_replies.py` — new
- `frontend/src/features/annotations/AnnotationItem.tsx` — add inline reply list + reply input
- `frontend/src/api/annotations.ts` — add reply endpoints
- `frontend/src/features/documents/insightPaneTabs.ts` — remove `"comments"` tab
- `frontend/src/features/documents/InsightPane.tsx` — remove comments tab, unify under annotations

**Approach:**
1. Migration: create `annotation_replies (id UUID PK, annotation_id UUID FK→annotations, user_id UUID FK→users, body TEXT NOT NULL, created_at TIMESTAMP, edited_at TIMESTAMP NULL, deleted_at TIMESTAMP NULL)`. Then INSERT all non-deleted `document_comments` rows as `annotations` with `position=NULL`, `text=body`, `user_id=author_id`, preserving `created_at`. Soft-deleted comments: migrate with `note="[deleted]"` to avoid content exposure.
2. Model update: add `reply_count: int = 0` to annotation list responses; `replies: list[AnnotationReply]` in detail fetch.
3. Router: add reply endpoints. Remove comments router from `main.py` include; keep file returning 410.
4. Frontend: collapse Comments tab. `AnnotationItem` renders a "Reply" button → inline composer.

**Verification:**
```bash
ruff check --fix src/ && mypy src --strict
pytest tests/unit/test_annotations_unified.py -q
pytest tests/integration/test_annotations_replies.py -q
npm run typecheck && npx vitest run src/features/annotations/
```

**Risks:**
- Migration is effectively one-way: downgrade restores the table but new replies live in `annotation_replies`. Document in migration downgrade comment.
- Keep comments router returning 410 for one release cycle in case external clients POST to it.

---

### #488 — Preserve document relationship structure for archives and email attachments

**Goal:** Add a `document_relationships` table to record parent/child provenance, populate during extraction, expose in the preview API, display context in the details panel.

**Assumptions:**
- `DocumentRow` has no `parent_id` today.
- Extraction/pipeline service creates child docs from ZIP/email and has access to parent `document_id`.
- `PreviewResponse` can be extended without breaking existing consumers.

**Out of scope:** Relationship-based search, hierarchical tree visualisation.

**Affected files:**
- `migrations/versions/<hash>_document_relationships.py` — new table
- `src/services/documents/models.py` — add `DocumentRelationship` model
- `src/services/documents/repository.py` — add relationship CRUD + `get_relationships(doc_id)`
- `src/services/extraction/` or `src/services/pipeline/` — record relationship on child doc creation (surgical 1–2 line addition)
- `src/services/api/schemas.py` — extend `PreviewResponse` with `relationships` field
- `src/services/api/routers/documents.py` — populate relationships in `/preview/{doc_id}`
- `tests/unit/test_document_relationships.py` — new
- `frontend/src/api/documents.ts` — add `relationships` field to `DocumentPreview` type
- `frontend/src/features/documents/DetailsTab.tsx` — add "Source context" section
- `frontend/src/features/documents/DetailsTab.test.tsx` — update

**Approach:**
1. Migration: create `document_relationships (id UUID PK, parent_document_id UUID FK→documents, child_document_id UUID FK→documents, relationship_type VARCHAR(30) NOT NULL — 'archive_child'|'email_attachment'|'nested', path_in_parent VARCHAR(500), created_at TIMESTAMP)`. Unique on `(parent_document_id, child_document_id)`.
2. Repository: `get_relationships(doc_id)` returns both upward (parents) and downward (children).
3. Pipeline wiring: in extraction step that creates child documents, call `repo.create_relationship(parent_id, child_id, type, path)`.
4. `PreviewResponse`: add `relationships: list[DocumentRelationshipInfo] | None = None` where `DocumentRelationshipInfo = {direction, type, other_document_id, title, path_in_parent}`.
5. `DetailsTab`: add "Source context" section that renders parent/sibling links when `preview.relationships` is non-empty. Sibling links navigate to `/documents/{id}`.

**Verification:**
```bash
ruff check --fix src/ && mypy src --strict
pytest tests/unit/test_document_relationships.py -q
npm run typecheck && npx vitest run src/features/documents/DetailsTab.test.tsx
```

**Risks:**
- Existing documents have no relationship rows — section stays hidden (empty guard in JSX).
- `path_in_parent` may be sensitive. Only render for users who have access to current doc (already gated by `assert_doc_access`). Show title of parent/siblings without path if access to those other docs is uncertain.

---

### #483 — Expand shown document details

**Goal:** Expand `DetailsTab.tsx` into grouped sections (File, Source, Processing, Intelligence, My Tags, Source Context, Metadata) using data from #486 (user tags), #488 (relationships), and existing entity/tag API calls.

**Assumptions:**
- #486 and #488 land first — if not, stub those sections.
- `InsightPane.tsx` already fetches entities (`getEntities`) and system tags (`getTags`).
- `PreviewResponse.metadata` dict is already returned.

**Out of scope:** Editing metadata fields inline, admin/debug-only field section (deferred).

**Affected files:**
- `frontend/src/features/documents/DetailsTab.tsx` — major expansion with grouped sections
- `frontend/src/features/documents/DetailsTab.module.css` — grouped section styles
- `frontend/src/features/documents/DetailsTab.test.tsx` — tests for all new sections
- `frontend/src/features/documents/InsightPane.tsx` — pass entities + system tags as props to `DetailsTab`
- `src/services/api/schemas.py` — add `indexed_at`, `tags`, `entities_summary` to `PreviewResponse`
- `src/services/api/routers/documents.py` — populate new fields in `/preview/{doc_id}`
- `tests/integration/test_documents_preview.py` — assert new fields

**Approach:**
1. Backend: extend `PreviewResponse` with `indexed_at: str | None`, `tags: list[str]`, `entities_summary: list[dict] | None`. Populate from existing intelligence/search repos inside the preview endpoint.
2. Group `DetailsTab` into `<section>` blocks:
   - **File** — filename, MIME type, extension, file size
   - **Source** — source name, source type, path (truncated + copy-full button)
   - **Processing** — status badge, ingested/indexed timestamps, version, SHA-256
   - **Intelligence** — entities (grouped by type), system tags
   - **My Tags** — `<UserTagEditor docId={docId} />` (from #486)
   - **Source Context** — relationships from #488 (parent/sibling links)
   - **Metadata** — collapsed `<details>` with key/value rows; "Show raw JSON" toggle
3. Long values: paths truncated at 60 chars in display; full value in `title` attr + copy button.
4. Empty handling: each section renders `null` when all its fields are absent.

**Verification:**
```bash
npm run typecheck
npx vitest run src/features/documents/DetailsTab.test.tsx
npx vitest run src/features/documents/InsightPane.test.tsx
pytest tests/integration/test_documents_preview.py -q
```

**Risks:**
- Bundling entities/tags into the preview endpoint adds latency. Consider a `?include_intelligence=true` query param to keep default fast, or rely on separate TanStack Query calls already made by `InsightPane`.

---

### #484 — Add advanced search with include/exclude and field-scoped filters

**Goal:** Add advanced search mode (filter drawer + optional query syntax) supporting include/exclude terms, phrase search, and field-scoped filters (path, source, filename, ext, tags, entities, metadata keys, date ranges).

**Assumptions:**
- `SearchRequest.filters: dict[str, Any]` exists and is forwarded to search backends.
- Meilisearch and Qdrant are the primary backends.
- `SearchFilters` frontend type has basic filtering; needs extension.

**Out of scope:** Saved advanced searches, entity-scoped vector search, full Elasticsearch migration, power-user query-string syntax parser (deferred to post-MVP).

**Affected files:**
- `src/services/api/schemas.py` — extend `SearchRequest` with structured filter fields
- `src/services/search/models.py` — add `AdvancedFilter`, `FieldFilter` types
- `src/services/search/hybrid.py` — parse and apply advanced filters
- `src/services/search/meili_provider.py` / `meili_types.py` — translate field filters to Meilisearch filter syntax
- `src/services/api/routers/search.py` — wire new fields through
- `tests/unit/test_advanced_search_filters.py` — new
- `frontend/src/api/search.ts` — extend `SearchFilters` with `include_terms`, `exclude_terms`, `path_prefix`, `source_type`, `extension`, `entity`, `metadata_filters`, `sort_by`, `sort_dir`
- `frontend/src/features/search/FilterPanel.tsx` — add advanced section
- `frontend/src/features/search/FilterPanel.test.tsx` — update
- `frontend/src/features/search/SearchPage.tsx` — wire new filter fields + accept initial filter state from URL params

**Approach:**
1. Backend: add to `SearchRequest`:
   ```python
   exclude_terms: list[str] = []
   field_filters: list[FieldFilter] = []  # {field, op, value}
   sort_by: Literal["relevance","updated_at","created_at","title"] = "relevance"
   sort_dir: Literal["asc","desc"] = "desc"
   ```
2. Filter dispatch in `hybrid.py`: `exclude_terms` → negative BM25 boost / post-filter. `field_filters` by field: `source`/`path`/`ext` → Meilisearch filter expression; `tags` → filter on indexed `tags` field; `metadata.*` → post-filter on fetched document metadata dict.
3. Check `meili_settings.py` — add `path` and `extension` to filterable attributes if missing.
4. Frontend `FilterPanel`: add collapsible "Advanced" section: Include chips input, Exclude chips input, Path starts-with text, Source type dropdown, Extension multi-select, Entity text input, Metadata key/value pair input.
5. `SearchPage`: read initial filter state from URL search params on mount (enables #489 linking).

**Verification:**
```bash
ruff check --fix src/ && mypy src --strict
pytest tests/unit/test_advanced_search_filters.py -q
npm run typecheck
npx vitest run src/features/search/FilterPanel.test.tsx
```

**Risks:**
- `metadata.*` filters are post-DB-fetch unless metadata is indexed in Meilisearch — may be slow for large result sets. Document as known limitation; add to `meili_settings.py` filterable list as a follow-up.
- `path` filterable attribute must be added to Meilisearch settings migration or it silently ignores the filter.

---

### #489 — Allow querying from document details values

**Goal:** Make selected `DetailsTab` values (source, path, type, tags, entities, metadata fields) clickable chips that navigate to search pre-populated with the matching field filter.

**Assumptions:**
- #483 (expanded details) is merged.
- #484 (advanced search with URL-driven initial filter state) is merged.
- TanStack Router is used — navigation carries state via URL search params.

**Out of scope:** Multi-value "add to filter" (click replaces, not appends), saving triggered search.

**Affected files:**
- `frontend/src/features/documents/FilterLink.tsx` — new: given `{field, value}`, builds search URL and renders as anchor/button with search icon
- `frontend/src/features/documents/FilterLink.test.tsx` — new
- `frontend/src/features/documents/DetailsTab.tsx` — wrap clickable values in `<FilterLink>`
- `frontend/src/api/search.ts` — add `buildSearchUrl(filters: SearchFilters): string` helper
- `frontend/src/features/search/SearchPage.tsx` — verify URL-param-driven initial filter state works (may already be done in #484)

**Approach:**
1. `buildSearchUrl`: serialise a `SearchFilters` object into URL search params for `/search` route.
2. `FilterLink`: `<Link to="/search" search={buildSearchParams(field, value)}>`. Renders inline with a small lucide `Search` icon. `aria-label="Search for documents with {field}: {value}"`.
3. `DetailsTab` wiring — wrap applicable Row values:
   - Source name → `source:"..."`
   - Path → `path_prefix:"..."`
   - Extension/MIME → `ext:...`
   - Each tag chip → `tag:"..."`
   - Each entity → `entity:"..."`
   - Each metadata key/value → `metadata.key:"value"`
4. `SearchPage`: confirm it reads initial filter from URL and pre-populates `FilterPanel` state.

**Verification:**
```bash
npm run typecheck
npx vitest run src/features/documents/FilterLink.test.tsx
npx vitest run src/features/documents/DetailsTab.test.tsx
```
Manual: open a document → click Source chip → confirm search opens with correct filter active.

**Risks:**
- If `SearchPage` URL-driven initial filter was not implemented in #484, this PR must add it — coordinate with #484 branch author.

---

## Integration Validation Checklist (pre–main merge)

Run on `feature/document-details-and-search` before final PR:

```bash
ruff check --fix src/ tests/ migrations/
ruff format src/ tests/ migrations/
mypy src --strict
pytest -q
npm run typecheck
npx vitest run
bash scripts/check-pr-cleanliness.sh main
```

Verify manually:
- [ ] Markdown files render with formatted HTML; Raw toggle shows plain text
- [ ] User tags save and reload; private tags not visible to other users
- [ ] Comments tab gone; annotation replies thread correctly; old comments appear as annotations
- [ ] ZIP/email child documents show "Source context" in details panel
- [ ] Details panel shows all grouped sections; missing fields hidden cleanly
- [ ] Advanced search filter drawer: include/exclude terms, source, path, extension, entity all applied correctly
- [ ] Clicking detail values navigates to search with correct pre-populated filter
- [ ] No agent artifacts in diff (`.opencode_auth.json`, `token_opencode.txt`, root-level `main`)
