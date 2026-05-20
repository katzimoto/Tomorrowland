# Document Viewer Design

**Status:** Draft  
**Date:** 2026-05-20  
**Branch:** `claude/design-document-viewer-j5CyA`

---

## Summary

This document proposes a high-fidelity document viewer for Tomorrowland that
renders uploaded files as close to their original appearance as technically
possible. The design preserves all existing functionality while adding real
rendering (PDF.js for PDFs, sandboxed HTML, native image controls) and a
cohesive viewer UX with fidelity transparency, metadata panels, and
accessibility improvements.

---

## A. Current-State Analysis

### What exists today

**Layout** (`DocumentPage.tsx`): Two-column layout — a `previewCol` (flex 3)
and an `insightCol` (flex 2) below a fixed toolbar. Mobile collapses to
stacked columns. The overall structure is sound and should be preserved.

**Toolbar** (`DocumentToolbar.tsx`): Back button, document title, translation
quality badge, translation version selector, "Request High-Quality Translation"
button, and download link.

**Preview pane** (`PreviewPane.tsx`): Dispatches on `mime_type` from the
preview API and renders the 2 000-char `snippet` field. All document renderers
today are text-based:

| Renderer | Used for | What it renders |
|---|---|---|
| `TextPreview` | plain, markdown, JSON, CSV, PDF, DOCX, RTF | `<pre>` of extracted text snippet |
| `HtmlPreview` | text/html | `dangerouslySetInnerHTML` of sanitized HTML (see security note) |
| `TablePreview` | XLSX, TSV | Parsed CSV rows in a `<table>` |
| `ArchivePreview` | ZIP, TAR | Filename list from snippet |
| `EmailPreview` | EML, MSG | Structured header/body view |
| `SlidesPreview` | PPTX | Extracted text, one block per slide |
| `ImagePreview` | image/* | `<img src="/api/download/docId">` |
| `UnsupportedPreview` | everything else | MIME label + download button |
| `ExtractionFailedPreview` / `FileMissingPreview` | error states | inline error UI |

**Insight pane** (`InsightPane.tsx`): Tabs — Summary, Q&A, Related, Annotations,
Comments, Subscriptions (stub), Versions.

**Backend preview API** (`GET /preview/{document_id}`): Returns a 2 000-char
`snippet`, `mime_type`, `translation_quality`, and metadata. Snippet is
generated server-side from `document_payloads.content_text` or extracted
on-the-fly from the file.

**Original file**: Available via `GET /download/{document_id}` as a raw byte
stream.

**Extraction**: `ExtractorRegistry` supports PDF, DOCX, PPTX, XLSX, ODT, RTF,
HTML, XML, JSON, CSV, plain text, ZIP, TAR, EML, MSG.

**Translation**: Two-tier — fast (LibreTranslate, at ingestion) and high
(LLM-based, on-demand). Multiple translation versions per document; current
version selector is in the toolbar.

### Current limitations

1. **No native rendering** — PDF, DOCX, PPTX all render as extracted plain
   text. Users see only 2 000 chars of extracted/translated content.
2. **Snippet truncation** — There is no API to fetch full document text; 2 000
   chars is the hard limit.
3. **HTML is not sandboxed** — `HtmlPreview` uses `dangerouslySetInnerHTML`
   after a client-side `DOMParser` strip. If the sanitizer is bypassed, JS can
   run in the app's origin.
4. **No fidelity indicator** — Users cannot tell whether they are seeing the
   original file, extracted text, or a translation.
5. **No page navigation** — Long or multi-page documents are presented as a
   single scrollable block.
6. **No zoom** — No zoom for images or PDFs.
7. **No view-mode switcher** — Users cannot switch between "original preview"
   and "extracted/translated text" from within the preview pane itself.
8. **No search within document** — There is no in-document text search or
   highlight capability.
9. **Missing file type renderers** — Audio, video, ODS, ODT visual preview, and
   SVG are not handled beyond the fallback.
10. **No conversion pipeline** — There is no server-side PDF/image conversion
    for Office files.

### Risks when changing the current implementation

- The `snippet` field and the `PreviewPane` dispatch switch are coupled; any
  renderer that needs more than 2 000 chars must use a new API endpoint.
- The toolbar's translation controls (version selector, quality badge, request
  button) must be preserved exactly.
- The insight pane tabs (Summary, Q&A, Related, Annotations, Comments,
  Versions) must remain fully functional.
- The `GET /download/{document_id}` endpoint is used by both the download
  button and `ImagePreview`; do not break its response headers.
- The translation polling loop in `DocumentPage` must continue to work
  correctly.
- The access control model (group-based ACL baked into search indexing) must
  not be affected.

---

## B. Target UX

### Main layout

```
┌─────────────────────────────────────────────────────────────────┐
│ TOOLBAR                                                          │
│ ← Back │ [FileIcon] Document Title      [Fidelity badge]        │
│         [View mode tabs] [Zoom −/+] [Page n/N] [Search ⌕]      │
│         [Translation selector] [Request HQ] [Download ↓]        │
├───────────────────────────────────────────┬─────────────────────┤
│                                           │                     │
│  VIEWER AREA                              │  INSIGHT PANE       │
│  (primary, flex 3)                        │  (flex 2, max 480px)│
│                                           │                     │
│  ┌──────────────────────────────────────┐ │  Tabs:              │
│  │                                      │ │  Summary / Q&A /    │
│  │   [rendered file content]            │ │  Related /          │
│  │                                      │ │  Annotations /      │
│  │                                      │ │  Comments /         │
│  └──────────────────────────────────────┘ │  Subscriptions /    │
│                                           │  Versions           │
│  [fidelity status bar]                    │                     │
└───────────────────────────────────────────┴─────────────────────┘
```

### Viewer modes

The toolbar exposes a **View Mode** control with up to four options, shown only
when the corresponding data exists for the document:

| Mode | Label | Condition |
|---|---|---|
| `original` | Original | File is stored and previewable in-browser |
| `preview` | Preview | Server-side converted preview (PDF/image) is available |
| `extracted` | Extracted text | Extraction succeeded |
| `translation` | Translation | At least one translation version exists |

The mode selector is not shown if only one mode is available; the pane renders
that mode silently.

### Fidelity status bar

A one-line status bar immediately below the viewer (not floating) communicates
what the user is seeing:

- `Viewing original file` (green dot)
- `Viewing converted preview — original available for download` (amber dot)
- `Viewing extracted text — original available for download` (amber dot)
- `Viewing translation (fast / high-quality) — original available for download`
  (amber or green dot)
- `Original file unavailable — showing extracted text` (red dot)
- `Preview conversion failed — showing extracted text` (amber dot)
- `No preview available — download original to view` (grey)

### Toolbar / actions (revised)

Keep everything that exists today; add:

- File type icon (from a MIME-to-icon map)
- View mode selector (new)
- In-document search button (opens a search bar below the toolbar)
- Page counter + prev/next arrows (shown only for paginated viewers: PDF,
  slides)
- Zoom controls (shown only for PDF and image viewers)

### Metadata panel

The existing DetailsPanel is not shown on the document page today. Add a
**Details** tab to the InsightPane (rightmost tab, or collapsible section in
the Summary tab) that surfaces:

- File type and MIME type
- File size
- Source / connector name and path
- Created, updated, imported timestamps
- Document language (source_language)
- Translation language (target_language)
- Processing status
- Content SHA-256 (truncated, for integrity)
- Version number / family

### Empty / loading / error states

| Scenario | Behaviour |
|---|---|
| Initial load | Skeleton rows in viewer and insight pane |
| Preview API error | EmptyState with title + retry button (existing) |
| Viewer loading (PDF / conversion) | Spinner overlay on viewer area, progress bar if paged |
| Preview conversion in progress | Inline banner in viewer: "Preview is being prepared…" with a spinner; polling every 5 s |
| Conversion failed | `ExtractionFailedPreview` with download button |
| File missing | `FileMissingPreview` with explanation |
| Unsupported type | `UnsupportedPreview` with MIME label + download button (existing) |
| Newer version exists | `VersionBanner` (existing) |
| Translation in progress | Existing polling + progress indicator in toolbar |

### Narrow / mobile layout

- Below 767 px: columns stack (existing behaviour).
- Toolbar wraps: view mode and zoom controls move to a secondary row or
  collapse into a `⋯` overflow menu.
- Insight pane appears below the viewer; default collapsed on mobile.
- Fidelity bar is always visible.
- Page navigation controls are sticky at the bottom of the viewer area on
  mobile for PDF.

---

## C. File Support Matrix

| File type / category | Preferred rendering | Fallback rendering | Search support | Metadata | Notes / risks |
|---|---|---|---|---|---|
| **PDF** | PDF.js inline viewer (pages, zoom, text layer, search) | Extracted text view | Yes (text layer) | Yes | Large PDFs: lazy page rendering; cap at configured max pages |
| **DOCX / DOC** | Server-side → PDF conversion, then PDF.js | Extracted text view | Via extracted text | Yes | Conversion via LibreOffice/unoconv; cache converted PDF |
| **ODT** | Server-side → PDF conversion, then PDF.js | Extracted text view | Via extracted text | Yes | Same pipeline as DOCX |
| **RTF** | Extracted text view (formatted) | Plain text | Via extracted text | Yes | Full RTF viewer not worth the cost; text extraction is high quality |
| **TXT** | Text viewer with wrap, line numbers, copy | — | Yes | Yes | |
| **Markdown** | Rendered HTML (remark/marked, sandboxed) | Raw text | Via extracted text | Yes | Sanitize output; no JS execution |
| **HTML** | Sandboxed `<iframe srcdoc>` | Stripped text | Via extracted text | Yes | **Security: must sandbox; current implementation is not sandboxed** |
| **XLSX / XLS** | TablePreview (parsed CSV grid, sheet tabs) | Extracted text | Partial (visible rows) | Yes | Limit display to first N rows; large files load lazily |
| **CSV / TSV** | TablePreview (parsed grid) | Plain text | Partial | Yes | Stream rows; cap at 10 000 visible |
| **ODS** | Server-side → CSV/PDF conversion, then grid | Extracted text | Partial | Yes | |
| **PPTX / PPT** | Server-side → PDF/image per slide, slide strip | Extracted text (slide per block) | Via extracted text | Yes | Slide strip sidebar; current SlidesPreview is text-only |
| **ODP** | Same as PPTX | Extracted text | Via extracted text | Yes | |
| **PNG / JPG / WEBP / GIF** | Native `<img>` with zoom/pan | — | No | Yes | GIF: native animation; no transcoding needed |
| **TIFF** | Server-side → PNG/WEBP, then `<img>` | Metadata only | No | Yes | Browser cannot render TIFF natively |
| **SVG** | Sandboxed `<img>` (not inline SVG) | Download only | No | Yes | Inline SVG execution risk; use `<img>` tag |
| **JSON** | Syntax-highlighted code viewer (collapsible tree optional) | Raw text | Yes | Yes | |
| **XML** | Syntax-highlighted code viewer | Raw text | Yes | Yes | |
| **YAML** | Syntax-highlighted code viewer | Raw text | Yes | Yes | |
| **Source code** | Syntax-highlighted code viewer (language detected) | Raw text | Yes | Yes | Use file extension for language hint |
| **Logs** | Text viewer, ANSI colour strip | Raw text | Yes | Yes | Cap at 50 000 lines; virtual scroll |
| **Audio** | Native `<audio>` controls + metadata + transcript if available | Metadata + download | No | Yes | Browser-native; no transcoding |
| **Video** | Native `<video>` controls + metadata | Metadata + download | No | Yes | Browser-native; large files: use byte-range streaming |
| **EML / MSG** | EmailPreview (structured header/body) | Extracted text | Via extracted text | Yes | Existing component, preserve it |
| **ZIP** | File tree list (ArchivePreview) | Filename list | No | Yes | Do not auto-extract; show inner preview if already extracted |
| **TAR / GZ** | File tree list (ArchivePreview) | Filename list | No | Yes | |
| **RAR / 7z** | File listing if supported by backend extractor | Metadata + download | No | Yes | Low priority |
| **Unknown / binary** | `UnsupportedPreview` (MIME + download) | — | No | Yes | |

---

## D. Technical Architecture

### Frontend components

```
DocumentPage
├── DocumentToolbar (extended)
│   ├── BackButton
│   ├── FileTypeIcon (new)
│   ├── DocumentTitle + TrustDisplay
│   ├── ViewModeSwitcher (new)   ← original / preview / extracted / translation
│   ├── ZoomControls (new)       ← shown for PDF + image only
│   ├── PageNavigation (new)     ← shown for PDF + slides only
│   ├── InDocumentSearchBar (new)
│   ├── TranslationVersionSelector (existing)
│   ├── RequestTranslationButton (existing)
│   └── DownloadButton (existing)
├── VersionBanner (existing)
├── FidelityStatusBar (new)      ← one-line, below toolbar
├── ViewerArea
│   └── PreviewPane (refactored)
│       ├── PdfViewer (new)      ← PDF.js worker
│       ├── ConvertedPreview (new) ← renders server-converted PDF
│       ├── ImageViewer (new)    ← zoom/pan, replaces ImagePreview
│       ├── HtmlPreview (fixed)  ← sandboxed iframe
│       ├── CodeViewer (new)     ← JSON/XML/YAML/source/logs
│       ├── TextPreview (existing, kept for plain/MD/RTF)
│       ├── TablePreview (existing, extended)
│       ├── ArchivePreview (existing)
│       ├── EmailPreview (existing)
│       ├── SlidesPreview (refactored) ← uses ConvertedPreview if PDF conversion exists
│       ├── MediaPreview (new)   ← audio/video
│       ├── UnsupportedPreview (existing)
│       ├── ExtractionFailedPreview (existing)
│       ├── FileMissingPreview (existing)
│       └── ConversionPendingPreview (new)
└── InsightPane (extended)
    └── Tabs: Summary / Q&A / Related / Annotations / Comments / Subscriptions / Versions / Details (new)
```

### New APIs needed

#### 1. Full text streaming endpoint

```
GET /documents/{document_id}/text
  ?translation_version_id=<uuid>
  &show_original=<bool>
  &offset=<int>
  &limit=<int>        (default 10 000 chars, max 100 000)
```

Returns `{ text, total_length, offset, truncated }`. This enables rendering
full documents without the 2 000-char snippet limit. Can be added alongside
the existing `/preview` endpoint with no breaking changes.

#### 2. Converted preview endpoint

```
GET /documents/{document_id}/converted-preview
  ?format=pdf          (default; also: image/png for thumbnails)
  ?page=<int>          (for image-per-page conversions)
```

Returns the converted file (PDF bytes or PNG bytes). If conversion is pending,
returns `202 Accepted` with `{ status: "pending" }`. If conversion failed,
returns `{ status: "failed", error: "..." }`.

The backend conversion pipeline produces the converted file once and caches it
(keyed by `content_sha256 + target_format`). Re-conversion is skipped if the
source file has not changed.

#### 3. Preview conversion status endpoint (or extend existing)

```
GET /documents/{document_id}/preview-status
```

Returns `{ conversion_status: "none" | "pending" | "ready" | "failed", has_converted_preview: bool }`.

Alternatively, extend the existing `GET /preview` response to include
`converted_preview_status`.

### Data model changes

**Minimal — avoid schema changes where possible.**

The only addition justified is a cache entry for converted previews:

```sql
-- New table: document_converted_previews
CREATE TABLE document_converted_previews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content_sha256  TEXT NOT NULL,   -- from source document
    target_format   TEXT NOT NULL,   -- e.g. 'pdf', 'image/png'
    stored_path     TEXT NOT NULL,   -- path to converted file on disk
    page_count      INT,             -- for PDF
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending / ready / failed
    error_summary   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, target_format)
);
```

This table is safe to add with no impact on existing functionality; it is only
read by the new conversion endpoint.

No changes to `documents`, `document_payloads`, `document_translation_versions`,
or `document_version_families` are required.

### Preview / conversion pipeline

```
Ingestion (existing)
  └── process_document job
        ├── extract text (existing)
        └── [new] enqueue convert_document_preview job
              └── convert_preview_worker
                    ├── run LibreOffice headless / unoconv → PDF
                    ├── store result in document_converted_previews
                    └── update status: ready / failed
```

The conversion worker runs the same durable claim-based job queue pattern as
`pipeline_jobs` — either add a new `job_type = "convert_preview"` or create a
dedicated `preview_conversion_jobs` table following the same schema.

**Conversion tool decision**: Use LibreOffice headless (already likely available
in the Docker environment, or easy to add to the `api` service image). No paid
cloud service is needed. LibreOffice handles DOCX, PPTX, XLSX, ODT, ODS, ODP,
and RTF → PDF conversion well.

LibreOffice is already the standard open-source choice for this type of
conversion in air-gapped deployments, which aligns with Tomorrowland's
air-gapped release requirement.

### Caching strategy

| Resource | Cache key | Cache location | Invalidation |
|---|---|---|---|
| Converted PDF / image | `content_sha256 + target_format` | `document_converted_previews.stored_path` | On document re-ingest with new sha256 |
| Preview snippet | `document_id + translation_version_id + show_original` | React Query (2 min stale time, existing) | On translation completion (existing polling) |
| Full document text | `document_id + version + offset` | React Query (5 min stale time) | On document update |
| PDF.js page renders | Managed by PDF.js internally | Browser memory | On viewer unmount |

### Security boundaries

**HTML preview** — Replace `dangerouslySetInnerHTML` with a sandboxed iframe:

```tsx
<iframe
  srcDoc={sanitizedHtml}
  sandbox="allow-same-origin"   // no allow-scripts
  title="HTML document preview"
  style={{ width: "100%", height: "100%", border: "none" }}
/>
```

`allow-same-origin` without `allow-scripts` gives the iframe its own DOM
without JS execution. Images and CSS load. This is safer than the current
approach and matches the approach used by most document preview tools.

**SVG** — Render via `<img src="/api/download/docId">`, never as inline SVG.
`<img>` prevents script execution in SVG files.

**HTML sanitization** (still needed for extracted text view): Keep server-side
`bleach`/`nh3`-style sanitization. Do not rely solely on client-side
`DOMParser`.

**Converted PDF** — PDFs served via the conversion endpoint are produced by
LibreOffice from uploaded Office files. They are benign in terms of macro
execution (macros do not survive conversion to PDF). PDF.js renders PDFs
without executing JavaScript — it is a JavaScript PDF renderer, not an Acrobat
plugin.

**Archive safety** — The existing `ZipExtractor` and `TarExtractor` do not
extract file contents; they list entries. The design preserves this. Archive
traversal (path components like `../../etc/passwd`) must be checked in the
extractor; add a test confirming this.

**Zip bombs** — Add a size check before extracting during conversion: abort if
uncompressed size exceeds a configurable limit (e.g. 500 MB).

**MIME sniffing** — The `/api/download/` response must set
`Content-Type: <mime>` and `X-Content-Type-Options: nosniff` to prevent
browsers from sniffing a downloaded file as HTML.

**Large file limits** — Configurable max file size per MIME category in
`Settings`. Conversion jobs should time out (e.g. 60 s) and mark status
`failed` rather than hanging.

**Malformed / corrupt files** — Conversion and extraction workers must catch
all exceptions and set `status = "failed"` with a summary. Never crash the
worker process on a malformed file.

### Error handling

| Failure | Frontend behaviour |
|---|---|
| Preview API 500 | EmptyState + retry button (existing) |
| Full text API error | Fall back to snippet; show fidelity bar warning |
| Conversion pending | `ConversionPendingPreview` with spinner + polling |
| Conversion failed | `ExtractionFailedPreview` + download button |
| PDF.js load error | Fall through to extracted text view; update fidelity bar |
| File missing on disk | `FileMissingPreview` (existing) |
| Translation in progress | Existing polling UX |
| Network timeout | Retry with exponential backoff (2/4/8 s) |

---

## E. Implementation Plan

### Phase 1 — Audit and preparation (no feature changes)

1. Read all existing renderer files and write a test inventory (which renderers
   have tests, which do not).
2. Confirm LibreOffice headless is available in or easily added to the Docker
   Compose service.
3. Confirm `X-Content-Type-Options: nosniff` is set on the download endpoint.
4. Confirm the existing `archive traversal` guard in ZipExtractor/TarExtractor;
   add a test if missing.
5. No code changes in this phase.

### Phase 2 — Fix critical security issue: sandbox HTML preview

**Scope**: Replace `dangerouslySetInnerHTML` in `HtmlPreview.tsx` with a
sandboxed `<iframe srcDoc>`.

**Risk**: Low. No API changes. No data model changes. The viewer renders the
same content, more safely.

**Files changed**: `HtmlPreview.tsx`, `HtmlPreview.test.tsx`

### Phase 3 — Add full text streaming API + viewer scrolling

**Scope**: Add `GET /documents/{document_id}/text` endpoint with
`offset`/`limit`. Extend `PreviewPane` to fetch full text for
text/markdown/code/CSV/plain document types (replacing the 2 000-char snippet).

**Risk**: Low. New endpoint; no changes to existing routes or data model. The
snippet endpoint remains for backwards compatibility.

**Files changed**:
- `src/services/api/routers/documents.py` (new route)
- `frontend/src/api/documents.ts` (new client function)
- `frontend/src/features/documents/PreviewPane.tsx`
- `frontend/src/features/documents/renderers/TextPreview.tsx`

### Phase 4 — Add PDF.js viewer for PDFs

**Scope**: Integrate PDF.js (via `pdfjs-dist`) into a new `PdfViewer` component.
Replace the `TextPreview` fallback for `application/pdf` with `PdfViewer`.
Add page navigation and zoom controls to the toolbar (shown only when PDF
is active). Add fidelity status bar.

**Risk**: Medium. PDF.js worker must be bundled or CDN-loaded. Large PDFs need
lazy page rendering. Need to test with malformed PDFs.

**Files changed**:
- `frontend/src/features/documents/renderers/PdfViewer.tsx` (new)
- `frontend/src/features/documents/PreviewPane.tsx`
- `frontend/src/features/documents/DocumentToolbar.tsx`
- `frontend/src/features/documents/FidelityStatusBar.tsx` (new)
- `frontend/package.json` (add `pdfjs-dist`)

### Phase 5 — Add view mode switcher + extracted/translation text modes

**Scope**: Add `ViewModeSwitcher` to toolbar. Wire up original / extracted /
translation modes. The extracted mode always fetches from the full text API
(Phase 3). The translation mode uses the existing `translation_version_id`
parameter. The original mode uses the `show_original=true` parameter (already
supported by the backend).

This phase makes the fidelity model explicit in the UI — users always know
what they are seeing.

**Risk**: Low. No backend changes. Re-uses existing API parameters.

**Files changed**:
- `frontend/src/features/documents/DocumentToolbar.tsx`
- `frontend/src/features/documents/DocumentPage.tsx`
- `frontend/src/features/documents/PreviewPane.tsx`

### Phase 6 — Add image viewer with zoom/pan

**Scope**: Replace the simple `<img>` in `ImagePreview` with an `ImageViewer`
component supporting zoom (CSS transform or dedicated library), pan (pointer
events), and keyboard shortcuts. Add TIFF → PNG server-side conversion (same
conversion worker from Phase 7). Add `<img>` rendering for SVG (replacing any
inline SVG path).

**Risk**: Low. Additive change. No API changes needed for JPG/PNG/WEBP/GIF.
TIFF requires the conversion endpoint.

**Files changed**:
- `frontend/src/features/documents/renderers/ImageViewer.tsx` (new)
- `frontend/src/features/documents/PreviewPane.tsx`

### Phase 7 — Add server-side Office → PDF conversion pipeline

**Scope**: Add `document_converted_previews` table, migration,
`convert_preview_worker`, and `GET /documents/{document_id}/converted-preview`
endpoint. Add `ConvertedPreview` frontend component. Wire DOCX/ODT → PDF
conversion into the pipeline (enqueue conversion job on ingestion). Update
`PreviewPane` to prefer converted PDF for DOCX/ODT/PPTX/ODP when available,
falling back to text.

**Risk**: High. Requires Docker image change (LibreOffice headless), new DB
table, new worker, new API. Must be deployed and tested in a dedicated feature
branch.

**Files changed**:
- `migrations/versions/<new>.py`
- `src/services/preview/converter.py` (new)
- `src/services/pipeline/convert_preview_worker.py` (new)
- `src/services/pipeline/jobs.py` (new job type)
- `src/services/api/routers/documents.py` (new routes)
- `frontend/src/api/documents.ts`
- `frontend/src/features/documents/renderers/ConvertedPreview.tsx` (new)
- `frontend/src/features/documents/renderers/ConversionPendingPreview.tsx` (new)
- `frontend/src/features/documents/PreviewPane.tsx`
- `docker-compose.yml` (add LibreOffice to api service if not present)

### Phase 8 — Add code/syntax viewer

**Scope**: Add `CodeViewer` component using a lightweight syntax highlighter
(e.g. `shiki` or `highlight.js`). Wire JSON, XML, YAML, and source code files
to `CodeViewer`. Replace the generic `TextPreview` for these types.

**Risk**: Low. Frontend only. No backend changes.

**Files changed**:
- `frontend/src/features/documents/renderers/CodeViewer.tsx` (new)
- `frontend/src/features/documents/PreviewPane.tsx`
- `frontend/package.json`

### Phase 9 — Add media viewer (audio/video)

**Scope**: Add `MediaPreview` component using native browser `<audio>` and
`<video>` elements with the existing `/api/download` URL. Show file metadata
(duration, codec if available from metadata). Show transcript if
`document_payloads.content_text` contains one.

**Risk**: Low. Native browser controls; no transcoding.

**Files changed**:
- `frontend/src/features/documents/renderers/MediaPreview.tsx` (new)
- `frontend/src/features/documents/PreviewPane.tsx`

### Phase 10 — Add metadata Details tab to InsightPane

**Scope**: Add a `DetailsTab` component inside `InsightPane` showing all
document metadata (file type, size, source, timestamps, language, status,
version). This replaces / augments the unused `DetailsPanel.tsx` component.

**Risk**: Low. Uses existing preview API response data. No backend changes.

**Files changed**:
- `frontend/src/features/documents/DetailsTab.tsx` (new)
- `frontend/src/features/documents/InsightPane.tsx`
- `frontend/src/features/documents/insightPaneTabs.ts`

### Phase 11 — In-document search and highlights

**Scope**: For PDF.js, enable the built-in text search. For text/code/HTML
viewers, implement a client-side find-in-page (regex match, highlight
occurrences, keyboard nav: Enter / Shift+Enter, Escape to close). For converted
previews (PDF output), search via PDF.js text layer.

**Risk**: Low for PDF (built-in). Medium for other types (custom highlight
logic).

**Files changed**:
- `frontend/src/features/documents/DocumentToolbar.tsx`
- `frontend/src/features/documents/renderers/PdfViewer.tsx`
- `frontend/src/features/documents/renderers/TextPreview.tsx`
- `frontend/src/features/documents/renderers/CodeViewer.tsx`

### Phase 12 — Accessibility and performance hardening

**Scope**:
- Keyboard navigation for all viewer controls (Tab, Arrow keys, Page Up/Down).
- `aria-label` on all icon buttons.
- Focus management when switching view modes.
- `alt` text for images (use title from metadata).
- Virtual scrolling for large text/CSV files (replace `<pre>` for >10 000 lines).
- Thumbnail strip for PDFs (lazy-loaded).
- `Content-Security-Policy` header review for iframe sandbox.
- Load time telemetry (hook into existing `measurePerformance` utility).

### Phase 13 — Tests

See Section F.

---

## F. Test Plan

### Frontend unit / component tests (Vitest + React Testing Library)

| Test area | What to verify |
|---|---|
| `PdfViewer` | Renders with mock PDF.js worker; shows page count; navigation buttons; keyboard prev/next |
| `HtmlPreview` | Renders sandboxed iframe; script tags in input do not appear in DOM; `sandbox` attribute is set |
| `ImageViewer` | Renders `<img>` with correct src; zoom in/out changes scale; keyboard +/- works |
| `CodeViewer` | Renders JSON with syntax highlighting; long lines wrap; copy button copies raw text |
| `TextPreview` | Renders full text (not truncated); virtual scroll activates above line threshold |
| `TablePreview` | Parses CSV; renders correct number of rows and columns; sheet tab switching (XLSX) |
| `ArchivePreview` | Lists filenames from snippet; path traversal entries (../../etc) are displayed but not navigable |
| `MediaPreview` | Renders `<audio>` / `<video>` element; transcript section shown when text present |
| `FidelityStatusBar` | Shows correct label for each fidelity mode; correct dot colour class |
| `ViewModeSwitcher` | Shows only available modes; fires `onModeChange`; hidden when only one mode |
| `ConversionPendingPreview` | Spinner shown; polling starts; switches to `ConvertedPreview` on status `ready` |
| `UnsupportedPreview` | Download button present; MIME type shown |
| `ExtractionFailedPreview` | Error message shown; download button present |
| `FileMissingPreview` | Error message shown; no download button |

### Backend unit tests

| Test area | What to verify |
|---|---|
| Full text API | Returns correct offset/limit slices; handles missing document; handles no translation |
| Converted preview API | Returns 200 with PDF bytes when ready; returns 202 when pending; returns error payload when failed |
| Preview status API | Returns correct status for each conversion state |
| `convert_preview_worker` | Invokes LibreOffice mock; writes to `document_converted_previews`; handles failure; handles timeout |
| `ZipExtractor` traversal guard | Path component `../../etc/passwd` does not escape the archive listing |
| Zip bomb guard | Uncompressed size > limit aborts extraction with error, not crash |
| Download endpoint headers | `Content-Type` matches `mime_type`; `X-Content-Type-Options: nosniff` present |

### Integration tests

| Test area | What to verify |
|---|---|
| PDF document end-to-end | Upload PDF → extract → index → preview API → PDF.js renders |
| DOCX conversion end-to-end | Upload DOCX → conversion job runs → converted-preview returns PDF bytes |
| Translation switching | Upload multi-language doc → fast translation → switch to original → switch to translation → correct snippet |
| Large file handling | Upload 50 MB PDF → viewer renders first page without loading full file |
| Corrupt PDF | Upload truncated PDF → extraction fails gracefully → ExtractionFailedPreview shown |
| Corrupt ZIP | Upload corrupt ZIP → listing fails → error state shown |
| Malformed HTML | Upload HTML with `<script>alert(1)</script>` → script tag removed in preview → no alert fires |
| SVG with script | Upload SVG with `<script>` → rendered as `<img>` not inline → no alert fires |
| Missing file on disk | Remove file from storage → FileMissingPreview shown |
| Conversion failure | LibreOffice fails → `failed` status → ExtractionFailedPreview shown with download |

### Accessibility tests (manual + automated)

| Test area | Method |
|---|---|
| Keyboard navigation through all toolbar controls | Manual + axe-core |
| Screen reader announces fidelity status bar | Manual with NVDA/VoiceOver |
| PDF page navigation by keyboard | Manual |
| Focus management on view mode switch | Manual + axe-core |
| Colour contrast of fidelity dot colours | axe-core |
| Download/open original always reachable | Verify no `display:none` on all states |

### Mobile layout tests

| Test area | Method |
|---|---|
| Toolbar wraps correctly at 375 px | Visual test / Playwright screenshot |
| Insight pane collapses on mobile | Manual |
| PDF navigation controls visible on mobile | Manual |

---

## MVP Scope (Recommended)

The highest-value improvements with the lowest risk, suitable for a first
release:

1. **Phase 2** (HTML sandbox fix) — Security fix, low risk, high value.
2. **Phase 3** (Full text API + text viewer) — Removes the 2 000-char
   truncation that makes the current viewer feel broken for real documents.
3. **Phase 4** (PDF.js viewer) — PDFs are the most common document type; native
   rendering is the single biggest UX improvement.
4. **Phase 5** (View mode switcher + fidelity bar) — Makes the experience
   transparent and trustworthy.
5. **Phase 6** (Image zoom/pan) — Low effort, high polish.
6. **Phase 10** (Metadata Details tab) — Uses existing data; gives the viewer
   completeness.

**MVP does not require**: server-side Office conversion (Phase 7), code viewer
(Phase 8), media viewer (Phase 9), or in-document search (Phase 11). Those are
valuable but independent.

---

## Later Enhancements (Post-MVP)

| Enhancement | Value | Complexity |
|---|---|---|
| Server-side Office → PDF conversion (Phase 7) | High — DOCX/PPTX users get real previews | High (LibreOffice worker, new job type, DB table) |
| Code/syntax viewer (Phase 8) | Medium — dev/analyst audience | Low |
| Media viewer with transcript (Phase 9) | Medium | Low |
| In-document search (Phase 11) | High for large docs | Medium |
| PPTX slide strip | Medium | Depends on Phase 7 conversion |
| XLSX sheet tabs + lazy row loading | Medium | Medium |
| Virtual scrolling for large text/CSV | Medium | Medium |
| Thumbnail strip for PDFs | Low-medium | Low (PDF.js built-in) |
| Archive inner-file preview | Low | Medium |
| OCR for scanned PDFs (image-only PDFs) | High for some content types | High (Tesseract integration) |
| Annotation anchoring to specific text spans | High for knowledge work | High |
| Print / export from viewer | Low | Low |

---

## GitHub Issues to Create

The following issues should be opened (one per phase to allow parallel-safe
independent agents):

| Issue | Title | Phase | Branch target |
|---|---|---|---|
| #A | Security: Sandbox HTML preview iframe (replace dangerouslySetInnerHTML) | 2 | `main` |
| #B | Full document text API endpoint (remove 2 000-char snippet limit) | 3 | `feature/document-viewer` |
| #C | PDF.js viewer for PDF documents | 4 | `feature/document-viewer` |
| #D | View mode switcher and fidelity status bar | 5 | `feature/document-viewer` |
| #E | Image viewer with zoom/pan | 6 | `feature/document-viewer` |
| #F | Metadata Details tab in InsightPane | 10 | `feature/document-viewer` |
| #G | Server-side Office → PDF conversion pipeline (LibreOffice worker) | 7 | `feature/document-viewer` |
| #H | Code/syntax viewer (JSON, XML, YAML, source files) | 8 | `feature/document-viewer` |
| #I | Media viewer for audio/video | 9 | `feature/document-viewer` |
| #J | In-document search and highlights | 11 | `feature/document-viewer` |
| #K | Accessibility and performance hardening | 12 | `feature/document-viewer` |
| #L | Document viewer test suite | 13 | `feature/document-viewer` |

Issue #A (HTML sandbox) should target `main` directly — it is an isolated
security fix with no dependencies.

Issues #B–#L should target a `feature/document-viewer` integration branch
following the project's feature branch policy.

---

## Context Loaded

- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `docs/agents/coding-behavior.md`
- `frontend/src/features/documents/DocumentPage.tsx`
- `frontend/src/features/documents/PreviewPane.tsx`
- `frontend/src/features/documents/DocumentToolbar.tsx`
- `frontend/src/features/documents/InsightPane.tsx`
- `frontend/src/features/documents/DocumentPage.module.css`
- `frontend/src/features/documents/renderers/TextPreview.tsx`
- `frontend/src/features/documents/renderers/HtmlPreview.tsx`
- Directory listings of `frontend/src/features/documents/` and `docs/design/`
- Explore agent survey (document model, APIs, extraction, translation, search,
  pipeline, all renderer components, API client types)

## Context Skipped

- `spec.md`, `spec-v4.pdf`
- `docs/context/*.md` area files (not needed for design-only task)
- Individual renderer files beyond TextPreview and HtmlPreview
- Backend service implementation files (survey results were sufficient)

## Token Efficiency Notes

- Used `rg` (via Explore agent) before opening files: yes
- Read more than one plan: no
- Read broad source areas: no — used targeted Explore agent + specific file reads
