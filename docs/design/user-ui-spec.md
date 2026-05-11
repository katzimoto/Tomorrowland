# User UI Product And Design Spec

## Purpose

This document defines the user-facing Tomorrowland interface for search,
document inspection, Q&A, comments, annotations, subscriptions, notifications,
and history. It is a product and interaction spec, not an implementation plan
for a specific frontend framework.

The experience should feel native on first use: obvious navigation, fast
feedback, familiar controls, restrained density, and no marketing-style landing
screen. The first screen is the working search app.

Detailed feature specs:

- `docs/design/document-comments-spec.md`
- `docs/design/translation-versions-spec.md`

## Design References

Use these as pattern references, not as visual copies:

- [Fluent 2 Searchbox](https://fluent2.microsoft.design/components/web/react/core/searchbox/usage/):
  search should support clear actions, optional filters, predictable focus
  behavior, recent topics, suggestions, and responsive layouts.
- [Carbon Search Pattern](https://carbondesignsystem.com/patterns/search-pattern/):
  search should make result counts visible, support keyboard operation, and
  keep focus stable while filters reload results.
- [Atlassian Dynamic Table](https://atlassian.design/components/dynamic-table/):
  dense operational lists should support sorting, pagination, and scannable
  row structure.
- [Atlassian Empty State](https://atlassian.design/components/empty-state):
  empty states should explain what happened and what the user can do next.
- [Material navigation rail guidance](https://www.sap.com/design-system/fiori-design-android/v25-8/components/m3-standard-components/navigation-rail/usage):
  medium and large screens should use a compact rail for three to seven primary
  app destinations.

## Experience Goals

- The user understands where to start within five seconds.
- Search, preview, and Q&A feel like one continuous workflow.
- Permissions are invisible when they work and clear when they block access.
- AI assistance feels grounded, cited, and subordinate to source documents.
- The UI feels like a native internal tool: quiet, fast, keyboard-friendly, and
  suited for repeated daily use.

## Non-Goals

- No marketing landing page.
- No decorative hero section.
- No oversized cards for basic operational content.
- No AI chat interface that hides the document search workflow.
- No admin UI in this spec except the entry point for users with admin rights.
- No dark mode in the MVP unless the product explicitly schedules it.

## Information Architecture

Primary navigation destinations:

- Search
- Q&A
- Subscriptions
- Notifications
- History
- Admin, visible only to admin users

Primary routes:

- `/search`
- `/doc/:doc_id`
- `/qa`
- `/subscriptions`
- `/notifications`
- `/history`
- `/settings/profile`
- `/admin`, admin users only

The default authenticated route is `/search`.

## Authentication UX

Authentication should feel like the front door to an internal tool, not a
separate product surface.

- `/login` is the only public route in the MVP.
- Login uses a compact form with email, password, submit, and one inline error
  region.
- Invalid credentials copy: `Email or password is incorrect.`
- Protected routes show an app loading state while the current user is checked.
  They must not flash navigation, search results, document titles, or previews
  before authorization is known.
- Expired sessions redirect to `/login?expired=1` and show:
  `Your session expired. Sign in again.`
- Logout clears local session state and returns to `/login`, even if the logout
  API call fails.
- Forbidden states use the same calm permission language as document access
  failures and must not reveal hidden source names, counts, or titles.
- Admin navigation appears only after the current user is confirmed as an admin.

## First-Run And Onboarding States

Tomorrowland should not depend on a tutorial to be usable. First-run states should
explain the current system state and give the next useful action.

### No Documents Indexed

Audience: any user when the corpus is empty.

Surface:

- Search workspace empty state.
- No filters shown except disabled placeholders.
- Recent searches and recent documents sections hidden.

Copy:

- Title: `No documents indexed yet`
- Body: `Search will become available after documents are ingested.`
- Primary action for admins: `Open admin setup`
- Secondary action for admins: `View ingestion sources`
- Regular users see no setup actions unless they are allowed to request access.

### No Accessible Sources

Audience: regular user with no group grants.

Copy:

- Title: `No accessible sources`
- Body: `Your account does not have access to any document sources yet.`
- Optional action: `Contact administrator`, if an admin contact is configured.

Do not show source names the user cannot access.

### Admin First Login

Audience: admin user before source configuration.

Use the search page, not a separate onboarding wizard. Show a compact setup
panel above the empty search state:

- Create or verify groups.
- Add ingestion source.
- Grant source permissions.
- Run initial sync.

The setup panel should disappear when at least one enabled source exists.

### Partially Indexed System

Audience: all users while ingestion is still running.

Show a subtle status line near the search header:

- `Indexing in progress`
- `Last indexed: 2 minutes ago`
- `Some new documents may not appear yet`

This status should never block search.

## App Shell

### Desktop Layout

Use a left navigation rail and a top utility bar.

- Left rail width: 72 px collapsed, 220 px expanded.
- Top utility height: 56 px.
- Content max width: none for app surfaces; use responsive grids instead.
- Search workspace uses full available width.
- Document preview uses split panes.

Left rail contents:

- Product mark: compact Tomorrowland wordmark or `N` mark.
- Primary nav icons with labels.
- Admin item separated by a divider when visible.
- Bottom area: profile/avatar and settings menu.

Top utility bar contents:

- Current surface title.
- Optional global quick search icon on non-search pages.
- Notification button with unread count.
- Profile menu.

### Tablet Layout

- Use collapsed rail by default.
- Filters become a slide-over panel.
- Document metadata panel collapses behind tabs.

### Mobile Layout

- Use bottom navigation for Search, Q&A, Notifications, History.
- Hide Subscriptions under More if needed.
- Search filters open as a full-screen sheet.
- Document preview uses stacked tabs: Preview, Details, Notes, Related.

## Low-Fidelity Wireframes

These wireframes are layout contracts, not pixel-perfect mockups.

### Search Workspace

```text
+---------------+-------------------------------------------------------------+
| N             | Search private knowledge                         Bell  User |
|               +-------------------------------------------------------------+
| Search        | +---------------------------------------------+  [Search]  |
| Q&A           | | vendor risk renewal                         |            |
| Subscriptions | +---------------------------------------------+            |
| Notifications | [Hybrid] [Keyword] [Semantic]  Sort: Relevance  Save       |
| History       |                                                             |
|               | Active filters: Source: Jira  Translation: High            |
| Admin         |                                                             |
|               | +------------ Filters ------------+ +---- Results -------+ |
|               | | Source                          | | Vendor Risk Review | |
|               | | File type                       | | PDF | High | Tags  | |
|               | | Date                            | | ...snippet...      | |
|               | | Tags                            | | Why this result?   | |
|               | | Language                        | +-------------------+ |
|               | | Translation                     | +-------------------+ |
|               | +---------------------------------+ | Jira LEGAL-482     | |
|               |                                     | ...snippet...      | |
|               |                                     +-------------------+ |
+---------------+-------------------------------------------------------------+
```

### Document Preview

```text
+---------------+-------------------------------------------------------------+
| Search        | <- Results  Vendor Risk Review 2025     Download Translate |
| Q&A           +-----------------------------------------------+-------------+
| Subscriptions |                                               | Summary     |
| Notifications |  Preview pane                                 | Details     |
| History       |  +-----------------------------------------+  | Notes       |
|               |  | Rendered text/html/table/image/email    |  | Related     |
| Admin         |  | content with in-document find controls   |  +-------------+
|               |  |                                         |  | Source      |
|               |  | Selection can create annotation          |  | Translation |
|               |  |                                         |  | Entities    |
|               |  +-----------------------------------------+  | Related docs|
+---------------+-----------------------------------------------+-------------+
```

### Q&A

```text
+---------------+-------------------------------------------------------------+
| Search        | Ask accessible documents                                    |
| Q&A           +-------------------------------------------------------------+
| Subscriptions | Scope: All accessible docs  Source: Any  Current filters    |
| Notifications | +-----------------------------------------------+ [Ask]     |
| History       | | What are the top renewal risks?               |           |
|               | +-----------------------------------------------+           |
| Admin         |                                                             |
|               | Answer                                                      |
|               | The main risks are supplier concentration...                |
|               |                                                             |
|               | Citations                                                   |
|               | +-------------------------------------------------------+   |
|               | | Vendor Risk Review 2025 | page 4 | score 0.82         |   |
|               | | ...matching chunk...                                  |   |
|               | +-------------------------------------------------------+   |
+---------------+-------------------------------------------------------------+
```

### Mobile Search

```text
+-------------------------------+
| Search                 Bell   |
+-------------------------------+
| +---------------------------+ |
| | vendor risk renewal       | |
| +---------------------------+ |
| [Hybrid]        Filter  Sort  |
| Source: Jira  High quality x  |
|                               |
| Vendor Risk Review 2025       |
| PDF | High translation        |
| ...snippet...                 |
|                               |
| Jira LEGAL-482                |
| ...snippet...                 |
+-------------------------------+
| Search  Q&A  Alerts  History  |
+-------------------------------+
```

## Visual Direction

The UI should be calm, high-trust, and information-rich.

### Palette

Avoid a one-note monochrome or purple-heavy palette. Use a neutral base with
small semantic accents:

- Background: `#F7F8FA`
- Surface: `#FFFFFF`
- Raised surface: `#FBFCFE`
- Border: `#D9DEE7`
- Text primary: `#111827`
- Text secondary: `#4B5563`
- Text muted: `#6B7280`
- Primary action: `#2563EB`
- Primary hover: `#1D4ED8`
- Success: `#0F766E`
- Warning: `#B45309`
- Danger: `#B42318`
- Source badge blue: `#1E40AF`
- Tag accent green: `#047857`
- Translation accent amber: `#B45309`

Use color sparingly. Most information hierarchy should come from spacing,
weight, borders, and layout.

### Dark Mode

Dark mode is not required for the MVP. If added later, it must be a complete
theme, not an inverted afterthought.

Dark mode token targets:

- Background: `#0F172A`
- Surface: `#111827`
- Raised surface: `#1F2937`
- Border: `#374151`
- Text primary: `#F9FAFB`
- Text secondary: `#D1D5DB`
- Text muted: `#9CA3AF`
- Primary action: `#60A5FA`
- Success: `#2DD4BF`
- Warning: `#FBBF24`
- Danger: `#F87171`

Dark mode acceptance:

- All preview modes remain readable.
- Syntax, tags, badges, and translation states meet WCAG AA contrast.
- Embedded document HTML is wrapped in a controlled theme container.
- Images and PDF previews are not color-inverted.

### Typography

Recommended stack:

```css
font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
  "Segoe UI", sans-serif;
```

Type scale:

- Page title: 24 px, 32 px line-height, 600 weight.
- Section title: 18 px, 26 px line-height, 600 weight.
- Panel title: 14 px, 20 px line-height, 600 weight.
- Body: 14 px, 20 px line-height, 400 weight.
- Metadata: 12 px, 16 px line-height, 500 weight.
- Button: 14 px, 20 px line-height, 500 weight.

Rules:

- Do not scale type with viewport width.
- Letter spacing is 0.
- Use compact headings inside panels.
- Avoid all-caps labels except tiny metadata chips when necessary.

### Spacing

Base spacing unit: 4 px.

- Page padding desktop: 24 px.
- Page padding mobile: 16 px.
- Panel gap: 16 px.
- Toolbar gap: 8 px.
- Row vertical padding: 14 px.
- Dense metadata gap: 6 px.

### Shape And Elevation

- Radius: 6 px for panels, controls, and repeated items.
- Radius: 4 px for chips and badges.
- Avoid nested cards.
- Use elevation only for menus, popovers, drawers, and modals.
- Search result rows can be bordered panels, not decorative floating cards.

## Core Interaction Model

Tomorrowland has one dominant loop:

1. Search or ask.
2. Open a document.
3. Inspect source content.
4. Ask a grounded question or annotate.
5. Save a subscription or return to results.

The UI should make that loop obvious through persistent back links, preserved
search state, and citation jumps back into documents.

## Trust And Provenance

Users need to know why a result or answer is credible without reading a manual.
The UI should make source, freshness, access, and processing state visible in a
low-friction way.

Show provenance in these places:

- Search result rows: source, type, indexed date, translation quality.
- Document toolbar: source label, external ID or path, indexed date.
- Q&A citations: document title, chunk text, source, and score.
- Details panel: ingestion source, original language, translation state, and
  source metadata.

Use concise trust labels:

- `Indexed from Folder`
- `Synced from Confluence`
- `Synced from Jira`
- `Published by NiFi`
- `Fast translation`
- `High quality translation`
- `Original language`

Avoid overstating confidence. Never label generated summaries, tags, entities,
or Q&A answers as authoritative.

## Search Workspace

### Route

`/search`

### Layout

Desktop:

- Header row with title and compact status.
- Search input row.
- Mode and sort toolbar.
- Left filter panel.
- Right results region.

Suggested desktop proportions:

- Filter panel: 280 px.
- Results region: remaining width.
- Results list max row width: 980 px.

### Search Input

Use a prominent searchbox, but keep it operational:

- Height: 44 px.
- Leading search icon.
- Clear button appears when query is non-empty.
- Search submit button to the right on desktop.
- Pressing Enter submits.
- On focus with empty query, show recent searches and saved topics.
- With typed query, show suggestions when available.

Placeholder examples:

- `Search documents, issues, pages, and emails`
- `Try "vendor risk renewal"`

### Search Modes

Use a segmented control:

- Hybrid
- Keyword
- Semantic

Default: Hybrid.

If backend only supports Hybrid at first, show only Hybrid until other modes are
real.

### Filters

Filters should be explicit, scan-friendly, and stable.

Filter groups:

- Source: Folder, NiFi, Confluence, Jira.
- File type: PDF, Office, Email, Archive, Text, Image.
- Date: Any time, last 7 days, last 30 days, custom range.
- Tags.
- Language.
- Translation: Original, Fast, High quality, Unknown.
- Permissions: hidden by default. Users should not need to think about this.

Filter behavior:

- Desktop filters are left-panel controls.
- Mobile filters are a full-screen sheet.
- Selected filters appear as removable chips above results.
- Result count updates after each filter change.
- Focus remains in the filter group after selection changes.

### Results

Each result row includes:

- Title.
- Source badge.
- File/type icon.
- Snippet with highlighted query terms.
- Tags, up to 4 visible plus `+N`.
- Translation quality.
- Last updated or indexed date.
- Optional summary line when available.
- Score explanation only behind an info tooltip.

### Component Anatomy

Result row:

- Fixed minimum height with reserved areas for icon, title, snippet, metadata,
  and actions.
- Left area: file/type icon and source badge.
- Main area: title, source path or issue key, snippet, optional summary, and
  tags.
- Right area: last updated/indexed date, translation quality, score tooltip, and
  icon actions.
- On mobile, actions collapse into an overflow menu and metadata wraps below
  the title. The row must not require horizontal scrolling.

Filter controls:

- Group label, selected count, options, and clear action.
- Selected filters also appear as removable chips above results.
- Long option names wrap inside the panel instead of resizing it.
- Unsupported filters are hidden when the API has no equivalent behavior.

Document toolbar:

- Left: back to search and document title truncation.
- Center: preview mode tabs or current preview mode label.
- Right: download, copy source path, request translation, subscribe, and more
  actions when available.
- Actions use icons with tooltips and accessible names.

Citation card:

- Source title, source badge, short quote, relevance/confidence label, and open
  action.
- The open action lands on the exact preview anchor when the backend provides
  one.
- Cards use a compact repeated-item style and must not look like nested panels.

### Ranking Transparency

Each search result should include a `Why this result?` popover or tooltip. It
should be compact and optional, never a permanent column.

Content:

- Matching terms or semantic similarity reason.
- Source and date contribution when relevant.
- Applied filters.
- Translation state.

Examples:

- `Matched "vendor risk" in body and title`
- `Semantically similar to your query`
- `Included by source filter: Jira`
- `Ranked lower because it is older than selected date range`

Do not expose inaccessible document counts or hidden source names.

Row actions:

- Open.
- Preview in side peek, optional later.
- Download, if available.
- Subscribe to similar topic, later phase.

Empty states:

- No query: show recent documents, recent searches, and saved subscriptions.
- No results: explain that no accessible documents match; suggest removing
  filters or trying broader terms.
- Permission-filtered zero results: do not reveal hidden documents.

Loading state:

- Use skeleton rows matching final result row height.
- Keep filters visible.

Error state:

- Preserve query and filters.
- Explain which backend is unavailable if known.
- Offer retry.

## Saved Searches

Saved searches and subscriptions are separate concepts.

Saved search:

- Passive shortcut to rerun a query and filters.
- No notifications.
- Appears on the search home empty state and command menu.
- Can be renamed, updated from current filters, or deleted.
- MVP persistence is local browser storage scoped by current user ID.
- Local saved searches are not shared across devices until a backend endpoint is
  added.

Subscription:

- Proactive alert rule.
- Generates notifications when new documents match.
- Has threshold, scope, and enabled state.

Save search action:

- Available from the search toolbar after a query or filter is active.
- Uses a bookmark icon and tooltip: `Save search`.
- Save dialog fields: name, query, filters summary.
- Dialog copy includes a subtle storage note: `Saved on this device.`

Do not turn every saved search into a subscription by default.

## Document Preview

### Route

`/doc/:doc_id`

### Layout

Desktop split:

- Main preview pane: 65 percent.
- Right insight pane: 35 percent, min 320 px, max 460 px.
- Top document toolbar spans both panes.

Document toolbar:

- Back to search.
- Document title.
- Source/type metadata.
- Translation version selector.
- Request translation button.
- Download icon button.
- More menu.

Right insight pane tabs:

- Summary
- Details
- Comments
- Annotations
- Related

The selected tab should persist per document while the user navigates within
the document.

### Preview Modes

Supported modes:

- `text`: monospace-optional text viewer with line wrapping and search-in-doc.
- `html`: sanitized rendered HTML with source-safe styling.
- `table`: virtualized table with frozen header, column resize, and row count.
- `slides`: slide list with title, content, notes, and slide index.
- `image`: zoomable image viewer with fit-to-width and actual-size controls.
- `archive`: file tree/list with path, size, and extract/download action later.
- `email`: message header, body, and attachment list.

Common preview controls:

- In-document find.
- Zoom where relevant.
- Copy selected text.
- Create annotation from selected text when annotations are enabled.
- Translation version selection where translated content exists.

### Preview Fallback States

Preview should fail gracefully and keep useful actions available.

Unsupported preview:

- Copy: `Preview is not available for this file type.`
- Show file metadata and Download action.

Extraction failed:

- Copy: `Text could not be extracted from this document.`
- Show Download action and document metadata.
- If translation was queued because extraction failed, show queue status.

File missing:

- Copy: `The source file is not available on disk.`
- Hide Download action.
- Show source path or external ID only if the user has document access.

Preview loading timeout:

- Copy: `Preview is taking longer than expected.`
- Keep retry and download actions visible.

Translation unavailable:

- Copy: `Translation is unavailable. Showing original content.`
- Keep request translation action available when allowed.

### Translation Status

Show translation status in the toolbar and details panel. When translation
versions are available, use the version selector and behavior from
`docs/design/translation-versions-spec.md`.

Labels:

- `Original`
- `Fast translation`
- `High quality translation`
- `Manual vN`
- `Manual vN pending`
- `Manual vN failed`
- `Translation unavailable`

Request translation button behavior:

- Visible when the user can request another translation version.
- Enabled when original, fast, unknown, or high quality content can be improved
  by a new manual request.
- Loading state after click.
- Success copy: `Translation requested`.
- Already queued copy: `Translation already queued`.

Version selection behavior:

- Do not hide original content when a translation is selected.
- Do not replace the current preview while a requested translation is pending.
- Preserve scroll position by anchor when switching versions, where possible.
- Support deep links to selected translation versions when authorized.

### Document Details

Details include:

- Source.
- File type.
- Language.
- Translation quality.
- Indexed date.
- Source path or external ID, truncated with copy action.
- Permissions summary: `Visible to your groups`, not raw group internals unless
  useful.

## Document Comments

Document comments are shared discussion attached to the whole document. They are
not anchored annotations.

Detailed behavior is defined in `docs/design/document-comments-spec.md`.

Summary:

- Comments live in the `Comments` tab of the document insight pane.
- Comments are visible to every user who can access the document.
- Comments are never visible to users without document access.
- Users can write plain text, long-form comments, line breaks, and Unicode
  emoji.
- There is no private/shared toggle for comments.
- Creators can edit or delete their own comments.
- Admins can edit or delete any comment.
- Admin edits and deletes must be audit-ready.
- Long comments collapse in the thread and expand without leaving the preview.

## Q&A

### Routes

- `/qa`
- Embedded Q&A panel on `/doc/:doc_id`

### Global Q&A

Layout:

- Prompt input at top.
- Scope controls below input.
- Answer region.
- Citation list.

Scope controls:

- All accessible documents.
- Current filters from last search.
- Selected sources.
- Current document, when launched from preview.

Answer requirements:

- Always show citations.
- Each citation links to document preview.
- Each citation includes title, source, snippet or chunk, and relevance score.
- If no supporting context exists, say no answer was found in accessible
  documents.

Q&A states:

- Loading: show retrieval and generation progress labels.
- Error: if model unavailable, show service unavailable and allow retry.
- Partial: if some sources fail, show a warning but preserve usable answer.

## Annotations

### Role

Annotations make document inspection collaborative without overwhelming the
reading experience. Use annotations for position-specific notes. Use document
comments for whole-document discussion.

### Interaction

- User selects text or region.
- A compact annotation popover appears.
- User writes note.
- User chooses Private or Shared when annotations support both modes.
- Saved annotation appears in right pane and inline marker.

Annotation list item:

- Author display name.
- Private/shared indicator.
- Selected quote.
- Note.
- Created/updated time.
- Jump to location action.
- Edit/delete actions where permitted.

Position shapes are defined in Phase 05 docs and should be reused exactly.

## Subscriptions

### Route

`/subscriptions`

### Purpose

Let users save topics and receive notifications when newly ingested documents
match.

List layout:

- Topic name.
- Query.
- Scope.
- Similarity threshold.
- Last matched.
- Unread count.
- Enabled switch.

Create/edit form:

- Topic name.
- Query text.
- Source scope.
- Threshold slider with numeric value.
- Preview matches button.

## Notifications

### Route

`/notifications`

Notification item:

- Topic/subscription name.
- Matched document title.
- Short reason/snippet.
- Source badge.
- Created time.
- Read/unread state.

Actions:

- Open document.
- Mark read.
- Mute subscription.

Unread count appears in the app shell notification button.

## History

### Route

`/history`

Sections:

- Recently viewed documents.
- Recent searches.
- Recent Q&A questions.
- Recent annotations.

Users should be able to clear personal history later, subject to audit policy.

## Expertise Map

### Route

`/expertise`

This feature should feel careful and respectful.

Search input:

- Topic query.

Result row:

- Person.
- Role or display metadata if available.
- Read count or contribution count.
- Top related documents.
- Reason label, for example: `Frequently reads matching documents`.

Do not imply endorsement or performance ranking. Use neutral language.

## Privacy And Sensitivity

Users should always understand what is private, shared, or auditable.

Privacy labels:

- `Private to you`
- `Shared with people who can access this document`
- `Visible to administrators`
- `Used for audit`

History:

- Personal history is visible to the user.
- Admin audit surfaces may show security-relevant activity.
- The History page should include a short privacy note in the page help menu,
  not as persistent body copy.

Annotations:

- Private annotations are visible only to their author.
- Shared annotations are visible only to users who can access the document.
- Admin delete rights should be represented as moderation, not ownership.

Expertise map:

- Use neutral copy and avoid leaderboard language.
- Explain why someone appears in a result.
- Do not show private annotations as evidence.

Q&A:

- Q&A must not use documents the user cannot access.
- Citations should never reveal inaccessible titles.

## Native-Feeling Details

### Keyboard Shortcuts

Shortcuts should exist but not be advertised as body text in the app. They can
appear in tooltips and command menu labels.

Recommended:

- `/`: focus search.
- `Esc`: close popover/drawer or clear transient selection.
- `Enter`: submit search or Q&A.
- `Cmd/Ctrl+K`: command menu.
- `J/K`: move result selection, optional power-user feature.

### Command Menu

Later enhancement:

- Search documents.
- Go to subscriptions.
- Open notifications.
- Create subscription from current search.
- Request translation for current document.

### Tooltips

Use tooltips for icon-only actions:

- Download.
- Request translation.
- Copy source path.
- Open related document.
- Mark read.

## Accessibility

Baseline requirements:

- Keyboard access for every interactive element.
- Visible focus ring: 2 px, primary color, offset 2 px.
- Color contrast at least WCAG AA.
- Result count announced after search/filter update.
- Filter changes preserve focus.
- Preview panes have semantic landmarks.
- Q&A citations are links with meaningful accessible names.
- Icon-only buttons require `aria-label`.
- Loading states use polite live regions where appropriate.

## Performance Requirements

- Initial app shell interactive within 2 seconds on the baseline device.
- Initial JavaScript for the authenticated shell should stay under 250 KB gzip.
- Route chunks should stay under 200 KB gzip unless a preview renderer is
  intentionally lazy-loaded and documented in the PR.
- CSS should stay under 80 KB gzip for the MVP.
- Route transitions show visible feedback within 100 ms.
- Cached route transitions complete within 500 ms on the baseline device.
- Search results skeleton appears within 150 ms after submit.
- Search results render progressively if backend latency exceeds 500 ms.
- Rendering 50 result rows should average under 8 ms per row on the baseline
  device, or the list should virtualize earlier.
- Result rows virtualize above 100 results.
- Table preview virtualizes rows above 200 rows.
- Image/PDF preview lazy-loads pages or tiles.
- Test against current Chrome, Edge, Firefox, and Safari 17 or newer.
- Baseline device: 4-core laptop CPU, 8 GB RAM, 1440 x 900 viewport.
- Mobile validation uses a throttled mid-range profile at 320 x 720 and
  390 x 844.

## Error And Permission Copy

Use plain, calm language.

Examples:

- No access: `You do not have access to this document.`
- Missing document: `This document was not found or is no longer indexed.`
- Search unavailable: `Search is temporarily unavailable. Try again in a moment.`
- Q&A unavailable: `The local Q&A model is not available right now.`
- Translation queued: `High quality translation queued.`
- Translation high quality: `This document already has a high quality translation.`

## Data Contracts Needed From Backend

Contract rules:

- Use UUID strings for document, source, annotation, and citation identifiers.
- Use ISO 8601 strings for dates.
- Use discriminated objects for preview payloads and annotation positions.
- Include preview anchors whenever search snippets, Q&A citations, or
  annotations can deep-link into a document.

Search result item:

```json
{
  "doc_id": "uuid",
  "source_id": "uuid",
  "external_id": "jira:ABC-123",
  "title": "string",
  "snippet": "string",
  "source": "folder|nifi|confluence|jira",
  "source_label": "string",
  "mime_type": "string",
  "tags": ["string"],
  "translation_quality": "fast|high|null",
  "score": 0.93,
  "updated_at": "iso-date",
  "indexed_at": "iso-date",
  "preview_anchor": {
    "anchor_id": "chunk-uuid",
    "label": "Page 4"
  },
  "why": [
    {
      "kind": "keyword|semantic|filter|translation|freshness",
      "label": "Matched vendor risk in body"
    }
  ]
}
```

Preview response:

```ts
type PreviewResponse = {
  doc_id: string;
  source_id: string;
  external_id: string | null;
  title: string;
  source: "folder" | "nifi" | "confluence" | "jira";
  source_label: string;
  mime_type: string;
  summary: string | null;
  tags: string[];
  entities: Array<{ name: string; type: string; confidence?: number }>;
  comment_count: number;
  annotations: Annotation[];
  translation_versions?: TranslationVersionsResponse;
  translation_quality: "fast" | "high" | null;
  related: RelatedDocument[];
  preview: PreviewPayload;
};

type PreviewPayload =
  | TextPreview
  | HtmlPreview
  | TablePreview
  | SlidesPreview
  | ImagePreview
  | ArchivePreview
  | EmailPreview
  | UnsupportedPreview;

type TextPreview = {
  mode: "text";
  content_type: "text/plain";
  text: string;
  anchors: Array<{
    anchor_id: string;
    label: string;
    start_char: number;
    end_char: number;
  }>;
};

type HtmlPreview = {
  mode: "html";
  content_type: "text/html";
  sanitized_html: string;
  anchors: Array<{ anchor_id: string; label: string; selector?: string }>;
};

type TablePreview = {
  mode: "table";
  content_type: "application/json";
  columns: Array<{
    key: string;
    label: string;
    type?: "string" | "number" | "date" | "boolean";
  }>;
  rows: Array<Record<string, string | number | boolean | null>>;
  total_rows: number;
};

type SlidesPreview = {
  mode: "slides";
  content_type: "application/json";
  slides: Array<{
    slide_id: string;
    title?: string;
    text: string;
    thumbnail_url?: string;
  }>;
};

type ImagePreview = {
  mode: "image";
  content_type: "image/png" | "image/jpeg" | "image/webp";
  image_url: string;
  width: number;
  height: number;
  alt_text?: string;
};

type ArchivePreview = {
  mode: "archive";
  content_type: "application/json";
  entries: Array<{
    path: string;
    size_bytes?: number;
    mime_type?: string;
    preview_doc_id?: string;
  }>;
};

type EmailPreview = {
  mode: "email";
  content_type: "application/json";
  from: string;
  to: string[];
  cc?: string[];
  sent_at?: string;
  subject: string;
  body_text: string;
  attachments: Array<{
    name: string;
    mime_type: string;
    preview_doc_id?: string;
  }>;
};

type UnsupportedPreview = {
  mode: "unsupported";
  content_type: string;
  reason: "unsupported_type" | "too_large" | "extraction_failed" | "not_found";
  message: string;
};
```

Q&A response:

```ts
type QaResponse = {
  answer: string;
  citations: Citation[];
  model: string;
  latency_ms: number;
};

type Citation = {
  citation_id: string;
  doc_id: string;
  chunk_id: string;
  title: string;
  source: "folder" | "nifi" | "confluence" | "jira";
  source_label: string;
  quote: string;
  score: number;
  preview_anchor: PreviewAnchor;
};

type PreviewAnchor = {
  anchor_id: string;
  label?: string;
  position:
    | { mode: "text-range"; start_char: number; end_char: number }
    | {
        mode: "page-region";
        page: number;
        x: number;
        y: number;
        width: number;
        height: number;
        unit: "ratio";
      }
    | { mode: "table-cell"; row: number; column_key: string }
    | { mode: "archive-entry"; path: string }
    | {
        mode: "email-section";
        section: "header" | "body" | "attachment";
        attachment_name?: string;
      };
};
```

Annotation response:

```ts
type Annotation = {
  annotation_id: string;
  doc_id: string;
  author_id: string;
  author_display_name: string;
  body: string;
  visibility: "private" | "source-readers";
  position: PreviewAnchor["position"];
  created_at: string;
  updated_at: string;
  can_edit: boolean;
  can_delete: boolean;
};
```

Document comments and translation version contracts are defined in:

- `docs/design/document-comments-spec.md`
- `docs/design/translation-versions-spec.md`

Related document:

```ts
type RelatedDocument = {
  doc_id: string;
  title: string;
  source_label: string;
  reason:
    | "same_source"
    | "shared_entities"
    | "semantic_similarity"
    | "linked_issue";
  score?: number;
};
```

## Empty State Requirements

Search home empty state:

- Show recent searches.
- Show recently viewed documents.
- Show saved subscriptions if any.

No results:

- State that no accessible documents matched.
- Show active filters.
- Offer clear filters button.

No annotations:

- Copy: `No annotations yet. Select text in the preview to add one.`

No comments:

- Copy: `No comments yet. Start a document discussion that everyone with access
  can see.`

No notifications:

- Copy: `No new matches. Subscription alerts will appear here.`

## UI Acceptance Checklist

Use this checklist during frontend review.

- First-run states exist for empty corpus, no accessible sources, and admin
  setup.
- Login, current-user loading, expired-session, logout, and forbidden states are
  covered by tests.
- Search, filters, and results preserve state when navigating to and from a
  document.
- Saved searches and subscriptions are visually and behaviorally distinct.
- Local saved searches are scoped by user ID and clearly marked as device-local.
- `Why this result?` is available without cluttering result rows.
- Preview fallback states preserve download or retry actions where applicable.
- Document comments support shared visibility, long text, emoji, creator
  edit/delete, and admin edit/delete.
- Translation versions can be requested, listed, selected, deep-linked, and
  shown without interrupting the current preview.
- Q&A answers always include citations or a clear no-context response.
- Preview, citation, comment, annotation, translation version, and
  related-document contracts use the documented shapes.
- Permission filtering never reveals inaccessible titles, source names, or
  counts.
- Performance budgets and the four required viewport checks are included in PR
  review artifacts.
- Privacy labels exist for annotations, history, audit-sensitive behavior, and
  expertise map evidence.
- Mobile layout has no overlapping text or controls at 320 px width.
- Keyboard navigation works for search, filters, result rows, tabs, dialogs,
  and popovers.
- Loading states reserve stable space and do not cause layout jumps.
- Empty states explain the situation and provide a next action.
- Dark mode is either fully implemented with tokens or absent from the MVP.

## Design Quality Checklist

- First screen is usable search, not a landing page.
- Search input, filters, and results are visible without scrolling on desktop.
- Main navigation has no more than six primary destinations.
- All icon-only buttons have tooltips and accessible names.
- Text never overlaps controls at mobile or desktop widths.
- Every loading state preserves layout dimensions.
- Empty states tell the user what happened and what to do next.
- Q&A answers always cite source documents.
- Permission filtering never reveals inaccessible document titles.
- Visual hierarchy comes from spacing and typography more than color.
- No nested cards.
- No decorative blobs, gradients, or oversized hero treatments.

## MVP Cut

Build first:

- App shell.
- Search workspace.
- Result list with filters.
- Document preview page.
- Download and request translation actions.
- Q&A panel with citations.

Build second:

- Annotations.
- Subscriptions.
- Notifications.
- History.

Build later:

- Expertise map.
- Command menu.
- Side peek preview from results.
- Personalized recent topic suggestions.
