# Mail + Office First Preview Architecture Review

Status: Approved 2026-06-12 (owner resolved the three open decisions: nh3
adopted; separate preview-worker image; all artifact-writing renders go
through the preview worker). Supersedes the PDF-first plan posted on #539,
2026-05-29.
Issue: #539 — high-fidelity document preview rendering pipeline
Author: Claude (architecture review pass, 2026-06-12)
Priority correction: Mail (EML/MSG) and Office (DOCX/PPTX/XLSX) are P0.
PDF is shared infrastructure, not the lead use case.

## Executive recommendation

Build the preview layer as a **manifest-first, artifact-backed renderer pipeline**
that reuses what already exists instead of inventing parallel infrastructure:

1. **One new table** (`document_preview_artifacts`, keyed by
   `document_id + content_sha256`) holding render status and a server-side
   manifest. Artifacts live on disk under `files_root/previews/`. No paths ever
   leave the backend; artifacts are addressed by opaque artifact IDs.
2. **Email first.** EML/MSG preview is a cheap, deterministic transform
   (stdlib `email` / already-present `extract-msg` parse → sanitized HTML +
   metadata + inline-image artifacts), rendered by the preview worker at
   first manifest request and cached. All artifact-writing renders go through
   the worker (owner decision): the API never writes to `files_data`, which
   stays mounted read-only.
3. **Office second**, same worker, heavier path: the existing
   `pipeline_jobs` + RabbitMQ machinery carries a new `preview_render` job
   type consumed by the `preview-worker` service. DOCX/PPTX convert via LibreOffice headless →
   `converted.pdf`, displayed by the **existing, already air-gapped pdf.js
   viewer**. XLSX does **not** go through PDF: it gets structured per-sheet
   grid artifacts with real sheet navigation.
4. **PDF/image previews are nearly free**: the manifest reports
   `renderer: pdfjs|image, status: ready` and the existing viewers keep
   reading `/api/download/{docId}`. This is where the old PDF-first plan and
   this plan converge — PDF becomes generic infrastructure, delivered last.
5. **Citations integrate through what already flows**: `page_number` →
   page/slide/sheet navigation unit, `text_excerpt` → in-viewer text search
   (the mechanism #536 already uses). Layout-block `bbox` overlays stay a
   reserved, non-blocking extension.

What carries over from the May 29 plan: the artifact table concept, the
artifact-serving endpoint with traversal protection, LibreOffice→PDF for
DOCX/PPTX, render-status polling, terminal-failure semantics, admin rerender.
What changes: email moves from slice 4 to slice 1; XLSX gets a dedicated
sheet-grid path; rendering jobs use the existing pipeline queue instead of
FastAPI `BackgroundTasks`; the container/attachment model becomes first-class;
sanitization is upgraded from the regex/HTMLParser approach (which already had
one XSS fixed in #623) for the adversarial email-HTML case.

## Current code findings

Investigated before proposing anything (file references are current `main`):

- **Preview service is on-demand and stateless.** `src/services/preview/service.py`
  produces a 2000-char `snippet` (translation version → payload → file
  re-extraction), tracks views, and contains the in-house allowlist HTML
  sanitizer (`_sanitize_html`, hardened in #623 after an attribute-breakout
  XSS). **No preview artifacts, thumbnails, or render cache exist anywhere.**
- **`PreviewResponse`** (`src/services/api/schemas.py:58–83`) is a stable
  contract (`snippet`, `mime_type`, `metadata`, `has_file`,
  `content_sha256`, `relationships`, `layout_blocks_summary`…). Additive
  changes only.
- **File serving is solid and reusable.** `GET /download/{document_id}`
  (`src/services/api/routers/documents.py:640–790`) streams with Range
  support, validates `target.is_relative_to(files_root)`, sets `nosniff`,
  falls back to payload text. Every document route enforces
  `assert_doc_access`.
- **Versioning is per-row.** A new version of a source item is a **new
  `documents` row** (`version_family_id`, `version_number`, `is_latest`,
  `content_sha256`, unique `(source_id, external_id, content_sha256)`). So
  `document_id + content_sha256` is already version-scoped.
- **Attachments are already child documents.** `parse_worker` creates child
  docs per attachment with sha-prefixed `external_id` (cycle/depth guards,
  #624) and records `document_relationships`
  (`relationship_type='attachment'`, `path_in_parent=filename`). The frontend
  shows these as links in `DetailsTab` ("Source context").
- **Extraction layer is mature** (31 extractors, parser router #668 with
  quality tiers and per-source policies, audit trail in
  `document_extractions`, admin visibility #670). `EmlExtractor`
  (`src/services/extraction/eml.py`) decodes RFC2047 headers, flattens
  text/html to text, and collects attachment bytes — but **discards HTML
  structure and inline (cid:) images**. `MsgExtractor` uses `extract-msg>=0.55`
  (already a **core** dependency) and can reach `msg.htmlBody`.
- **Layout metadata exists but is text-anchored.** `document_layout_blocks`
  (#669) has `page_number`, `block_type`, `reading_order`, and an **unused
  `bbox` column**; blocks derive from `LocationSegment`s
  (`extraction_metadata` on `document_payloads`, #530). PDF segments carry
  page numbers; PPTX segments carry slide numbers.
- **Citations flow as `document_id + page_number + chunk_index +
  text_excerpt`** (`frontend/src/api/chat.ts`). #536's click-to-highlight is
  `PreviewWithHighlight` → `PreviewPane` with `initialPage` +
  `searchQuery=text_excerpt`; viewers highlight by text search, not offsets.
- **Frontend viewers**: `PreviewPane.tsx` is a MIME dispatcher over 12+
  renderers. `PdfViewer` is **pdf.js bundled locally (air-gapped), with page
  nav, zoom, initial-page-from-citation, and in-document search** — the single
  most reusable asset. `EmailPreview`, `SlidesPreview`, `TablePreview` are all
  extracted-text renderers (XLSX loses multi-sheet structure entirely).
- **Job infrastructure is ready.** `pipeline_jobs` has claim/retry/dead-letter,
  a unique active-job index per `(document_id, job_type)` (no stampedes),
  stale-lock reaping, and admin requeue. Adding a job type is a string + a
  `BaseConsumer` subclass + a compose service. `legacy_office.py` already
  demonstrates the guarded `soffice --headless` subprocess pattern (30s
  timeout, empty-result degradation).
- **Airgap constraints**: one shared backend image (`python:3.13-slim`; no
  LibreOffice/poppler/tesseract today), split image parts for offline install,
  `files_data:/data` volume shared API↔workers (API mounts read-only today —
  see Risks), per-worker cpu/mem/pids limits in compose.
- **Docling (#649/PR #735, merged)** is an optional HIGH-tier *extraction*
  backend. It is the future supplier of `bbox` layout data; it is **not** part
  of this preview pipeline and its scope is not duplicated here.

## Priority file-type model

### Mail: EML / MSG

The wedge. An analyst must see the email as an email: headers, recipients,
the styled body, inline images, the reply chain, and the attachments — and be
able to jump from a citation into it.

- **EML (P0, slice 1)**: full structured preview — metadata header, sanitized
  HTML body (or text body), cid: inline images served as artifacts, quoted
  replies collapsible, attachments linked to their child documents.
- **MSG (P0, slice 2, reduced fidelity)**: realistic *now* because
  `extract-msg` is already a core dep and exposes `htmlBody`. When the body is
  HTML → same sanitization path as EML. When the body is RTF-only (common for
  Outlook-internal mail) → plain-text body fallback; RTF→HTML conversion is
  explicitly staged behind a follow-up issue (new dependency decision).
- **MIME text/plain and text/html** standalone documents reuse the same
  sanitizer module via the existing `HtmlPreview` path.

### Office: DOCX / PPTX / XLSX

- **DOCX + PPTX (P0, slice 3)**: LibreOffice headless → `converted.pdf`
  artifact, rendered by the existing pdf.js viewer (page/slide navigation,
  zoom, search come for free). Extracted-text renderers remain the fallback
  whenever conversion is unavailable, failed, or disabled.
- **XLSX (P0, slice 4)**: spreadsheets paginate terribly through PDF (wide
  sheets shred into page fragments). Instead: per-sheet **grid artifacts**
  (JSON cell grids via `openpyxl`, row/col capped) + a `SheetViewer` with real
  sheet tabs. Table/number fidelity beats pixel fidelity for sheets.
  LibreOffice→PDF for sheets can be added later as an optional "print view".
- Legacy formats (DOC/PPT/XLS) ride the same LibreOffice path when
  `soffice` is present; otherwise text fallback.

### PDF / image as shared infrastructure

PDF and images already have high-fidelity, air-gapped viewers fed by
`/api/download/{docId}`. They join the manifest model trivially
(`renderer: pdfjs|image`, `status: ready`, no artifacts) so every file type
reports through one status/navigation contract. Server-side page images are
**not** built in this issue — pdf.js renders client-side; that decision from
the May 29 plan stands. Thumbnails are optional and deferred (poppler
dependency decision).

## Proposed architecture

```text
                      GET /preview/{id}/manifest
                                 │
                    ┌────────────┴─────────────┐
                    │ document_preview_artifacts│  (status + manifest + file map)
                    └────────────┬─────────────┘
              row missing        │        row present
        ┌──────────┴───────────┐ │ ┌────────────────────┐
        │ no-artifact kind?    │ │ │ return manifest    │
        │ (pdf/image/text)     │ │ │ (ready/partial/    │
        │  → persist ready     │ │ │  failed/pending)   │
        │    manifest inline   │ │ └────────────────────┘
        │ artifact kind?       │
        │ (email/office)       │
        │  → enqueue           │
        │    preview_render    │
        │    job, return       │
        │    status=pending    │
        └──────────────────────┘
                                  preview-worker (BaseConsumer)
                                  email parse → body/cid artifacts
                                  soffice --headless → converted.pdf
                                  openpyxl → sheet grids
                                  writes files_root/previews/{doc}/{sha}/
                                  marks ready|partial|failed (terminal)
```

Normalized preview tree (what the manifest expresses for every type):

```text
PreviewDocument
  ├── status / renderer / error
  ├── primary body (email html/text, converted.pdf, sheet grids, raw file)
  ├── navigation (pages | slides | sheets | none)
  ├── artifacts (opaque IDs → served by artifact endpoint)
  ├── attachments (→ child document IDs, each with its own manifest)
  └── evidence capabilities (anchor unit, text-search support, regions flag)
```

Direct answers to the design questions:

| # | Question | Decision |
|---|---|---|
| 1 | Canonical email preview model | Structured manifest + artifacts (header metadata, sanitized HTML body, text body, quoted ranges, inline-image artifacts, attachment refs) — not a single HTML blob |
| 2 | Email as document vs container | Both: the EML/MSG `documents` row is the preview root; attachments stay child documents (existing model) referenced from the manifest |
| 3 | Citation jumps | Citation `document_id` already distinguishes body (email doc) vs attachment (child doc). Body: text-excerpt search; quoted section: auto-expand the section containing the match; Office: `page_number` → page/slide/sheet nav unit + text search |
| 4 | Attachment connection | Reuse `document_relationships`; manifest embeds `{filename, content_type, size, document_id, preview_available}`; child docs render a parent-context banner |
| 5 | Artifact storage | Hybrid: filesystem (`files_root/previews/{document_id}/{content_sha256}/`) + DB status/manifest row. No blobs in DB, no object store (none exists) |
| 6 | Manifest schema | See next section |
| 7 | Manifest scope | Per document × content_sha256 (= version-scoped, since versions are separate document rows). Attachment-scoped manifests exist per child doc; container composition is by reference |
| 8 | Cache invalidation | sha256 in the unique key; re-ingest → new doc row → new manifest; changed sha on same row → stale row superseded; admin rerender deletes row + dir; orphan-dir sweep as admin maintenance |
| 9 | API endpoints | `GET …/manifest`, `GET …/artifact/{artifact_id}`, `GET …/thumbnail`, `POST /admin/preview/{id}/rerender` (below) |
| 10 | Safe UI fetching | Opaque artifact IDs + ACL on every route + CSP/sandbox for HTML artifacts; binary types via existing `/download` |
| 11 | Failed/partial states | Persisted `status` + `error_category` (+ admin-only detail); `partial` = subset of artifacts usable; `failed` is terminal (no auto-retry) |
| 12 | Job queue/retry | Existing `pipeline_jobs` + RabbitMQ; new `preview_render` job type + `preview-worker`; dead-letter + admin requeue reused as-is |
| 13 | Office path | Both: LibreOffice headless → PDF (DOCX/PPTX visual) AND structured extraction (XLSX grids); extracted-text fallback always present |
| 14 | EML path | stdlib `email` parse → sanitize → artifacts; never render raw HTML; never fetch remote resources |
| 15 | MSG now? | Yes, at reduced fidelity (htmlBody or text). RTF-body conversion staged behind a follow-up dependency decision |
| 16 | HTML sanitization | `nh3` allowlist sanitizer (approved 2026-06-12; see Security) + sandboxed iframe + CSP; remote img/css/forms/scripts stripped; `cid:` rewritten to artifact URLs |
| 17 | Highlight mapping | Now: `page_number`→nav unit + text search. Reserved: `extraction_metadata` char offsets → body regions; `document_layout_blocks.bbox` → visual overlays (Docling supplies bbox later) |

## Preview manifest schema

API response (`PreviewManifestResponse`). Server-internal fields (paths,
filenames) are never serialized:

```json
{
  "document_id": "uuid",
  "cache_key": "sha256:3f7a…",
  "kind": "email | office_doc | office_slides | office_sheets | pdf | image | text",
  "renderer": "email | libreoffice_pdf | sheet_grid | pdfjs | image | text",
  "status": "pending | running | ready | partial | failed",
  "error": { "category": "render_timeout", "detail": null },
  "generated_at": "iso8601",
  "navigation": {
    "unit": "page | slide | sheet | none",
    "count": 3,
    "items": [ { "index": 1, "label": "Q1 Budget", "artifact_id": "sheet-1" } ]
  },
  "artifacts": [
    { "id": "body-html", "role": "email_body_html", "content_type": "text/html", "size_bytes": 18234 },
    { "id": "converted-pdf", "role": "office_pdf", "content_type": "application/pdf", "size_bytes": 412345 }
  ],
  "email": {
    "subject": "…", "from": "…", "to": ["…"], "cc": [], "bcc": [],
    "date": "iso8601", "message_id": "<…>",
    "has_html_body": true, "has_text_body": true,
    "quoted_ranges": [ { "artifact_region": "q1", "label": "On … wrote:" } ],
    "inline_images": [ { "artifact_id": "cid-1", "content_type": "image/png" } ],
    "blocked_remote_images": 3,
    "attachments": [
      { "filename": "contract.pdf", "content_type": "application/pdf",
        "size_bytes": 102400, "document_id": "uuid-or-null",
        "preview_available": true, "inline": false }
    ]
  },
  "office": { "pdf_artifact_id": "converted-pdf", "page_count": 12, "text_fallback": true },
  "evidence": {
    "supports_text_search": true,
    "anchor_unit": "page | slide | sheet | body",
    "regions_available": false
  }
}
```

Notes:

- `error.detail` is populated only for admins (`require_admin`-style check in
  the router); non-admins see `category` only.
- `status=pending|running` includes a `retry_after_ms` hint; the endpoint
  always returns 200 with the status in-body (simpler client contract than
  202 semantics).
- For `pdf|image|text` kinds the manifest is computed and persisted on first
  request with `status: ready` and zero artifacts — viewers keep using
  `/api/download/{docId}` and `/documents/{id}/text`.

DB table (Alembic migration, upgrade + downgrade):

```sql
CREATE TABLE document_preview_artifacts (
    id              UUID PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content_sha256  TEXT NOT NULL,
    renderer        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    manifest        JSON,            -- API manifest body (no paths)
    files           JSON,            -- internal: {artifact_id: relative_filename}
    error_category  TEXT,
    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (document_id, content_sha256)
);
CREATE INDEX ix_preview_artifacts_document_id ON document_preview_artifacts(document_id);
```

Disk layout: `files_root/previews/{document_id}/{content_sha256}/` containing
e.g. `body.html`, `body.txt`, `cid-1.png`, `converted.pdf`, `sheet-1.json`.
The `files` map is the only path source; artifact serving resolves
`artifact_id → relative filename → files_root-validated absolute path`
(same `is_relative_to` guard as the download route).

## Mail preview model

Renderer: `src/services/preview/renderers/email_renderer.py`.

1. **Parse** with stdlib `email` (`policy=email.policy.default`) for EML;
   `extract_msg` for MSG. Never reuse the text-flattening `EmlExtractor` —
   preview needs the MIME tree, not flattened text. (Extraction behavior is
   untouched; this is a parallel read of the same bytes.)
2. **Metadata header**: subject, from, to, cc, bcc (bcc is present in
   sent-items exports), date, message-id, in-reply-to — RFC2047-decoded.
   Stored in the manifest, not as an artifact.
3. **Body selection**: prefer `text/html` part (sanitized → `body.html`),
   always also store `text/plain` (→ `body.txt`) when present. The viewer
   offers an HTML/text toggle; text is the search/citation surface.
4. **Sanitization** (see Security): scripts, event handlers, forms, iframes,
   objects, `<meta>` redirects, external stylesheets removed; `style`
   attributes stripped in v1; `img src` policy:
   - `cid:xyz` → matched to MIME parts by Content-ID, payload written as
     `cid-N` artifact (size/count capped), `src` rewritten to
     `/api/preview/{id}/artifact/cid-N`;
   - `http(s)://`, `data:` → removed, replaced by a placeholder element;
     count surfaced as `blocked_remote_images` (tracking-pixel defense).
   - `a href` → kept for `http(s)` but rendered inert in the viewer
     (`target=_blank rel=noopener`, click-through warning optional later);
     all other schemes stripped.
5. **Quoted replies / thread history**: heuristic segmentation —
   `<blockquote>` chains in HTML, `>`-prefixed runs and "On … wrote:" /
   "-----Original Message-----" markers in text. Sections are wrapped in
   `<details>`-style collapsible regions and listed as `quoted_ranges`.
   Heuristic-only, explicitly non-blocking: a wrong split degrades to "shown
   expanded", never to data loss.
6. **Attachments**: listed from the MIME tree; each entry is joined against
   `document_relationships` children of this document to resolve
   `document_id` (match on `path_in_parent` filename; see Risks #6 for the
   duplicate-filename caveat). Entries without a child doc (skipped by
   extractor guards) render as metadata-only rows.
7. **Caching**: email rendering is cheap and bounded
   (`PREVIEW_MAX_FILE_BYTES` gate) but still runs **in the preview worker**
   (owner decision — the API keeps its read-only `files_data` mount). First
   view enqueues the job and shows the pending state briefly; the render
   itself is sub-second, so the polling hook resolves on its first or second
   tick. ETag = `content_sha256` on artifact responses. If first-view latency
   ever matters, eager mail rendering at ingest (parse_worker publishes the
   preview job) is the lever — noted as a follow-up, not built in v1.

## Office preview model

Renderer split by sub-kind:

- **DOCX / PPTX / (DOC, PPT, RTF, ODT, ODP when soffice present)** —
  `src/services/preview/renderers/office_pdf.py`:
  `soffice --headless --norestore --convert-to pdf --outdir {dir} {input}`
  with per-job `-env:UserInstallation=file:///tmp/{job}` isolation,
  `subprocess.run(timeout=PREVIEW_RENDER_TIMEOUT_SECONDS)` (pattern lifted
  from `legacy_office.py`), page count read post-hoc (pypdf, already a dep)
  and capped by `PREVIEW_MAX_PAGES` → `partial` if exceeded.
  Output: `converted.pdf` artifact; `navigation.unit = page|slide`.
  Frontend renders it with the existing pdf.js viewer.
- **XLSX / (XLS, ODS)** — `src/services/preview/renderers/sheet_grid.py`:
  `openpyxl` (data-only) → one `sheet-N.json` artifact per sheet:
  `{name, rows: [[cell,…]], merged: […], truncated: {rows, cols}}`, capped at
  `PREVIEW_MAX_SHEET_ROWS`/`COLS`; `navigation.unit = sheet`, items labeled
  with sheet names. Formulas render as computed values (data-only mode);
  charts/images are out of scope v1 (noted in manifest as `truncated`
  diagnostics).
- **Extracted-text fallback** is not an artifact — it's the existing
  `/documents/{id}/text` path, flagged via `office.text_fallback: true`, and
  is what the UI shows for `status: failed|pending`.
- Office rendering always runs in the **preview worker**, never in the API
  process (soffice is heavy, needs its own container limits).

## Attachment and container-document model

No schema change needed — the container model already exists:

- Email/archive → child documents via `parse_worker` (`relationship_type`
  `attachment`, sha-suffixed `external_id`, cycle/depth guards from #624).
- The manifest makes it navigable: parent manifest lists attachments with
  child `document_id`s; clicking routes to `/doc/{child_id}` whose own
  manifest drives its preview (an attached DOCX gets the Office path, an
  attached PDF gets pdf.js, a nested EML gets the email path).
- **New**: a parent-context banner on any document that has a `parent`
  relationship ("Attachment of: {email subject} — open email"), built from
  the `relationships` field already present in `PreviewResponse`.
- Citations that land on an attachment need no special casing — the
  citation's `document_id` *is* the child document. The banner supplies the
  evidence context ("this came from that email").

## Backend changes

```text
src/services/preview/
  service.py                  unchanged (snippet/view/auto-enrich contract preserved)
  manifest_service.py         NEW — manifest assembly, render dispatch, status logic
  artifact_repository.py      NEW — document_preview_artifacts CRUD
  artifact_store.py           NEW — previews/ dir layout, write/serve/delete, sweep
  sanitizer.py                NEW — email/office HTML sanitizer (shared; see Security)
  renderers/
    base.py                   NEW — PreviewRenderer protocol + registry
                                    (mirrors ExtractorRegistry quality-tier pattern)
    email_renderer.py         NEW — EML/MSG (slices 1–3)
    office_pdf.py             NEW — LibreOffice→PDF (slice 4)
    sheet_grid.py             NEW — XLSX grids (slice 5)
src/services/pipeline/
  preview_worker.py           NEW — BaseConsumer, queue document.preview.requested
                                    (ships in S1: email renders here too)
  publisher.py                +routing key "preview": "document.preview.requested"
src/services/api/routers/
  preview_manifest.py         NEW router (manifest/artifact/thumbnail/rerender)
src/shared/config.py          +settings (below)
migrations/versions/…         +document_preview_artifacts (upgrade+downgrade)
docker/preview-worker.Dockerfile  NEW — FROM the backend image, adds LibreOffice
                                  + fonts (approved: separate image target so only
                                  the preview worker carries soffice; release
                                  tooling adds it to the airgap split-parts bundle)
docker-compose*.yml           +preview-worker service (parse-worker template;
                              backend image in S1, soffice image from S4)
pyproject.toml                +console script tomorrowland-preview-worker; +nh3 (approved)
```

New settings (env, `Settings`):

```text
ENABLE_PREVIEW_RENDER=true          # gates Office job enqueue + worker; manifest
                                    # endpoint itself always works (text fallback)
PREVIEW_MAX_FILE_BYTES=104857600    # 100 MB gate before any render
PREVIEW_RENDER_TIMEOUT_SECONDS=120  # soffice subprocess kill
PREVIEW_MAX_PAGES=500
PREVIEW_MAX_SHEET_ROWS=5000
PREVIEW_MAX_SHEET_COLS=200
PREVIEW_MAX_INLINE_IMAGES=50
PREVIEW_MAX_INLINE_IMAGE_BYTES=5242880
```

Env-only gating (like `ENABLE_OCR`/`ENABLE_DOCLING`) — this is renderer
infrastructure, not a user-facing feature flag; no dual DB gate, no 404
behavior, graceful text fallback when off.

## API changes

All routes ACL-checked with the existing `assert_doc_access`; admin route uses
the existing admin guard. No internal paths in any response.

```text
GET  /preview/{document_id}/manifest
     → PreviewManifestResponse (200 always; status in body)
     → side effect: ready-immediate manifest (pdf/image/text) or
       preview_render job enqueue (email + office)

GET  /preview/{document_id}/artifact/{artifact_id}
     → FileResponse; artifact_id resolved via the DB `files` map only
       (no client-supplied filenames → no traversal surface);
       headers: X-Content-Type-Options: nosniff, ETag: content_sha256,
       Cache-Control: private, max-age=86400;
       for text/html artifacts additionally:
       Content-Security-Policy: default-src 'none';
         img-src 'self'; style-src 'unsafe-inline'
       Content-Disposition: inline

GET  /preview/{document_id}/thumbnail
     → 404 in v1 unless a thumb artifact exists (deferred; field reserved)

POST /admin/preview/{document_id}/rerender
     → deletes artifact row + directory, re-dispatches; returns {status: pending}
```

Existing `GET /preview/{document_id}` and `GET /download/{document_id}` are
untouched; `PreviewResponse` is untouched (the manifest is a sibling endpoint,
not a mutation of the snippet contract).

## Frontend changes

```text
frontend/src/api/preview.ts                 NEW — types + usePreviewManifest
                                            (TanStack Query, refetchInterval while
                                             pending/running, capped backoff)
frontend/src/features/documents/PreviewPane.tsx
    manifest-first dispatch on manifest.renderer; falls through to the
    current MIME dispatch whenever the manifest is absent/disabled/failed
    → zero regression by construction
frontend/src/features/documents/renderers/
  EmailViewer.tsx              NEW — header card; sandboxed iframe
                               (sandbox="" — no scripts, no same-origin needed
                               since images are absolute /api URLs); html/text
                               toggle; collapsible quoted sections;
                               blocked-remote-images notice; attachment list
                               with links + preview-availability badges.
                               Implements searchQuery/activeSearchIndex/
                               onMatchCountChange against body text (viewer
                               contract from PreviewPane)
  SheetViewer.tsx              NEW — sheet tabs from navigation.items;
                               virtualized grid (react-window v2 List,
                               rowProps={{}} — decision 2026-05-21); per-cell
                               search match counting like TablePreview
  PdfViewer.tsx                small change — accept optional `src` prop
                               (default stays /api/download/{docId}) so
                               renderer=libreoffice_pdf passes the artifact URL
  ParentContextBanner.tsx      NEW — "Attachment of …" from existing
                               relationships data
  RendererStatusBadge.tsx      NEW — admin-only status + Re-render button
frontend/src/i18n/locales/en.ts  + preview.* strings (typed dictionary)
```

States: `pending/running` → "Preparing preview…" spinner over the text
fallback; `failed` → text fallback + non-blocking notice (admins see
`error.category`/detail + rerender); `partial` → render what exists + warning
banner. `EmailPreview` stays as the fallback for manifest-less email docs.

## Queue/cache/invalidation model

- **Dispatch**: manifest request finds no row → insert `status=pending`.
  No-artifact kinds (pdf/image/text) flip to `ready` in the same request
  (manifest only, no disk writes). Artifact kinds (email and office) always
  `enqueue_document(job_type="preview_render")` + publish
  `document.preview.requested` — the API process never writes artifacts
  (owner decision; `files_data` stays read-only in the API container). The
  existing unique active-job index on `(document_id, job_type)` prevents
  duplicate renders under concurrent first views.
- **Worker**: `preview_worker.py` (BaseConsumer) claims the job, runs the
  renderer with subprocess timeout, writes artifacts, marks the artifact row
  `ready|partial|failed` and the job `succeeded` (a *render* failure is a
  *successful* job that recorded a failed render — prevents infinite
  pipeline retries for deterministic failures like corrupt files).
  Transient infra errors (disk, DB) use `mark_retry` normally.
- **Terminal failure**: `status=failed` never auto-rerenders. Only
  `POST /admin/preview/{id}/rerender` (or a content change) resets it. This
  satisfies the "broken file must not retry forever" constraint twice over.
- **Invalidation**: new document version = new row + new sha → fresh manifest
  on first view; superseded rows/dirs are garbage. Cleanup: delete artifact
  rows by FK cascade with the document; an orphan-directory sweep utility
  ships as an admin/maintenance follow-up (not load-bearing for correctness).
- **Eager vs lazy**: v1 is lazy (first view). Eager mail rendering at ingest
  is a one-line follow-up (parse_worker publishes preview after relationships
  are recorded) once volume justifies it.

## Security and airgap constraints

Checklist (all enforced by code in the slices, all testable):

1. **HTML sanitization — the load-bearing control.** Email HTML is the most
   adversarial input in the product. **Approved 2026-06-12: adopt `nh3`**
   (Rust/ammonia, single offline wheel, no network, actively maintained)
   with an explicit allowlist: structural/text tags + `table` family +
   `img[src]`/`a[href]` with URL-scheme filtering; `style` attributes stripped
   in v1. Rationale: the in-house HTMLParser sanitizer already had one
   attribute-breakout/entity-smuggle XSS (#623), and email HTML is
   exactly where hand-rolled sanitizers fail. This consciously updates
   decision 2026-06-01/#623 ("dependency-free for air-gap") **for preview
   sanitization only** — nh3 is air-gap compatible (wheel in the lockfile,
   baked into the image). The existing snippet sanitizer in
   `preview/service.py` is untouched by this plan.
2. **Defense in depth regardless of sanitizer**: HTML artifacts are served
   with a deny-all CSP and rendered inside `<iframe sandbox>` (no scripts, no
   forms, no top-navigation), so a sanitizer miss is contained twice.
3. **No remote fetches**: remote `img/link/@import` stripped at sanitize time
   (tracking pixels included, with a visible blocked count); iframe CSP blocks
   anything missed; soffice runs headless with isolated `UserInstallation`
   (and the preview-worker container can be denied egress at the compose
   level — it only needs postgres/rabbitmq).
4. **No macro execution**: LibreOffice CLI `--convert-to` does not execute
   document macros; `--norestore` + fresh profile per job removes state
   carryover; nothing in the email path executes anything.
5. **No path exposure**: artifact IDs are opaque; the `files` map is
   server-side; resolved paths re-validated with `is_relative_to(files_root)`
   exactly like the download route.
6. **Limits**: file-size gate before render; subprocess timeout with kill;
   page/sheet/inline-image caps → `partial`, not OOM; worker container keeps
   the standard cpu/mem/pids limits (soffice gets its own service so a heavy
   conversion can't starve the API).
7. **Failure persistence**: failed is terminal (admin-only reset) — no retry
   loops on corrupt/oversized files.
8. **Airgap packaging**: nh3 → uv.lock → image; LibreOffice → debian packages
   in the backend image (size tradeoff in Risks #2); no CDN, no fonts
   download (install `fonts-liberation` + `fonts-dejavu` with LibreOffice for
   sane substitution of common Office fonts).
9. **ACL**: every new route calls `assert_doc_access`; artifact access is
   per-document, so attachment ACL follows the child document's source
   grants (consistent with existing behavior).

## Integration with citations/layout metadata

- **Today (ships with the slices)**: `PreviewWithHighlight` already passes
  `initialPage` + `searchQuery`. Mapping: `page_number` → pdf.js page
  (DOCX/PPTX converted PDFs and native PDFs), → sheet index (XLSX, once sheet
  segments exist — see below), → ignored for email (body is unit-less);
  `text_excerpt` → existing in-viewer text search in EmailViewer (body text),
  SheetViewer (cells), pdf.js (extracted page text). A citation that matches
  inside a collapsed quoted section auto-expands it.
- **Small additive extraction change** (flagged, not a chunking rebuild): the
  XLSX extractor should emit per-sheet `LocationSegment`s
  (`page_number = sheet index`) so sheet-level citation anchoring works like
  PPTX slides. PPTX already emits slide numbers; PDF emits pages; DOCX has no
  page concept at extraction time (see Risks #5).
- **Reserved (explicitly not built now)**: `evidence.regions_available` and a
  future `regions` artifact mapping `extraction_metadata` char offsets and
  `document_layout_blocks` rows (`block_type`, `reading_order`, `bbox`) onto
  body regions / page overlays. The manifest shape accommodates it without
  breaking changes; Docling (#649) is the expected `bbox` supplier; pdf.js
  text-layer coordinates are the expected PDF-side anchor. Per #539
  non-goals, no bounding-box overlays in the first implementation.

## Test plan

Fixtures (extends the #671 corpus — currently has **zero** mail fixtures):

```text
tests/fixtures/mail/
  plain.eml                    text-only body
  html-inline.eml              HTML body + cid: inline image + remote <img>
  thread.eml                   quoted reply chain (blockquote + "On … wrote:")
  attachments.eml              PDF + DOCX + nested .eml attachments
  malicious.eml                XSS corpus body (script/onerror/javascript:/
                               attribute-breakout/entity-smuggle from #623,
                               form, meta-refresh, tracking pixel)
  sample.msg                   htmlBody variant; rtf-only variant if obtainable
```

Backend unit (`tests/unit/test_preview_manifest.py`, `test_email_renderer.py`,
`test_sheet_grid.py`, `test_office_pdf.py`):
sanitizer XSS corpus (every malicious.eml vector neutralized); cid rewrite +
remote-image block counts; quoted-range segmentation; MSG html/text fallback;
manifest assembly per kind; sheet row/col truncation; soffice subprocess
mocked: success / timeout / missing binary / non-zero exit → correct
ready/failed/partial + error categories; oversized file gate; renderer
registry dispatch.

Backend integration (`tests/integration/test_preview_manifest_api.py`,
via `migrated_engine`, no Docker):
manifest lifecycle (pending → ready) for email and office alike (job row
asserted, worker invoked directly — no RabbitMQ needed); artifact serving + unknown
`artifact_id` → 404; ACL → 403/404 for non-granted user; admin rerender resets
failed; non-admin rerender rejected; two versions (different sha) → distinct
manifests; corrupt file → terminal failed; `ENABLE_PREVIEW_RENDER=false` →
text-fallback manifest. (Per tl-backend-integration-test: explicit Settings
overrides, no Meilisearch dependency.)

Frontend (Vitest/jsdom):
PreviewPane manifest dispatch + fallback-to-MIME path; EmailViewer states
(html/text toggle, quoted collapse/expand, attachment links, blocked-images
notice, search match counting); SheetViewer tab nav + truncation banner;
pending/failed/partial states; PdfViewer `src` prop; ResizeObserver mock for
virtualized grid (decision 2026-05-21).

Gates per AGENTS.md: ruff, ruff format, mypy --strict, targeted pytest,
`npm run typecheck`, targeted vitest, `mkdocs build --strict` for the docs
slice.

## Implementation slices

Feature branch **`feature/preview-rendering`** (multi-issue,
schema+backend+frontend coordination → feature-branch policy applies). One
sub-issue per slice; merge order matches the shared-file policy
(schema → backend → frontend → docs/changelog).

1. **S1 — Manifest foundation + EML preview (backend)**: migration,
   artifact repository/store, nh3 sanitizer, email renderer, **preview-worker
   service + `preview_render` job type** (runs on the plain backend image —
   no soffice yet), manifest + artifact + rerender endpoints, mail fixture
   corpus, unit + integration tests. Office kinds report
   `renderer: text, status: ready` (honest fallback) until S4.
2. **S2 — EML preview (frontend)**: `usePreviewManifest`, PreviewPane
   manifest dispatch, EmailViewer, ParentContextBanner, i18n, vitest.
   *Mail wedge demoable end-to-end after S2.*
3. **S3 — MSG**: htmlBody → same path; text fallback; fixtures; staged
   RTF-body follow-up issue created.
4. **S4 — Office DOCX/PPTX**: `docker/preview-worker.Dockerfile` (LibreOffice
   + fonts) + compose/airgap split-parts wiring + office_pdf renderer +
   PdfViewer `src` prop.
5. **S5 — XLSX sheet grids**: sheet_grid renderer + SheetViewer + per-sheet
   location segments (small extraction addition).
6. **S6 — PDF/image/text manifest integration + admin diagnostics**:
   ready-immediate manifests, RendererStatusBadge + rerender UI, partial-state
   surfacing, orphan-dir sweep utility.
7. **S7 — Docs + CHANGELOG + integration validation** on the feature branch;
   final PR to main with the validation summary.

Each slice is independently shippable and leaves `main`-bound state
consistent; if the schedule forces a cut, S1–S2 alone deliver the strategic
mail capability.

## Risks / decisions needed

1. ~~nh3 dependency vs in-house sanitizer~~ — **RESOLVED 2026-06-12: nh3
   adopted** for preview sanitization (scoped update to #623's
   dependency-free decision; the existing snippet sanitizer is untouched).
2. ~~LibreOffice image placement~~ — **RESOLVED 2026-06-12: separate
   Dockerfile target** (`docker/preview-worker.Dockerfile` FROM the backend
   image); only the preview worker carries soffice. Residual task: release
   tooling must add the image to the airgap split-parts bundle (S4,
   coordinate with release owner).
3. ~~API write access to `files_data`~~ — **RESOLVED 2026-06-12: all
   artifact-writing renders (email included) go through the preview
   worker.** The API keeps its read-only mount. Residual consequence: email
   first view shows a brief pending state (job round-trip, sub-second
   render); eager mail rendering at ingest remains the latency lever if
   needed later.
4. **DOCX page anchoring is approximate**: extraction has no page concept for
   DOCX, and LibreOffice pagination ≠ Word pagination. Citations into DOCX
   visual previews therefore anchor by text search, not page number. Honest
   limitation to state in the issue; exact page anchors hold for
   PDF/PPTX(slides)/XLSX(sheets).
5. **XLSX fidelity ceiling**: grids carry values, not charts/conditional
   formatting. Accepted for v1; "LibreOffice print view" is the optional
   later add-on.
6. **Duplicate attachment filenames** make `path_in_parent` matching
   ambiguous. Mitigation: match on (filename, order); proper fix is storing
   the attachment index or sha12 in `path_in_parent` at parse time (small
   additive change in parse_worker, coordinate with pipeline owners).
7. **MSG RTF-only bodies** degrade to plain text until an RTF→HTML decision
   (new dependency) — staged follow-up issue.
8. **Sweep/retention**: superseded artifact dirs accumulate until the S6
   sweep ships; bounded by document version churn, not by views. Acceptable
   short-term.

---

## Context Loaded
- `AGENTS.md`, `docs/agents/token-efficiency.md`, `CLAUDE.md`
- Issue #539 body + existing 2026-05-29 plan comment; PR #735 description
- `docs/memory/decisions.md`, `docs/memory/current-state.md`
- Fan-out code investigation (4 parallel read-only agents): preview/document
  backend, extraction/parser-router/layout, citations/frontend viewers,
  jobs/airgap/docker

## Context Skipped
- `spec.md` / `spec-v4.pdf` (not authorized)
- `docs/agents/coding-behavior.md` (planning-only task)
- Full source reads outside the investigation scope; PR #735 diff (merged,
  out of scope)

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used search-first discovery before opening files: yes (delegated rg-based
  exploration)
- Read more than one plan: yes — the prior #539 plan comment, required because
  this review supersedes it
- Read broad source areas: via scoped sub-agents only; main context held
  summaries, not file dumps
