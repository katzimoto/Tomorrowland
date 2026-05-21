---
name: tl-new-viewer-component
description: >
  Use this skill when adding a new document preview component to Tomorrowland's viewer
  system, or when wiring a new MIME type to PreviewPane. Invoke it whenever the work
  involves: creating a viewer (TextPreview/PdfViewer/ImageViewer/CodeViewer/MediaPreview
  style), adding a MIME dispatch branch to PreviewPane, threading viewer state through
  DocumentPage or DocumentToolbar, adding react-window virtualization, writing jsdom tests
  for a viewer component, debugging why a viewer isn't rendering, or adding in-document
  search support to a viewer. Use it proactively — the prop threading and mock requirements
  are non-obvious and consistently cause test failures when skipped.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: implementation-agents
---

# tl-new-viewer-component

## Purpose

Every new document viewer follows a consistent integration pattern. Knowing it before opening files prevents the most common mistakes: wrong MIME dispatch order, missing props, broken state threading, and absent jsdom mocks that make tests pass locally but fail in CI.

## PreviewPane MIME dispatch

`src/features/documents/PreviewPane.tsx` is the MIME dispatcher. Add your viewer branch in the correct position — more specific before generic, or your MIME will be swallowed by an earlier fallback:

```
application/pdf          → PdfViewer
CODE_MIMES set           → CodeViewer  (json, xml, yaml, source types)
audio/* / video/*        → MediaPreview
image/*                  → ImageViewer
text/*                   → TextPreview  ← generic fallback
archive/*                → ArchivePreview
```

`TIFF` → `<UnsupportedPreview />`. Encrypted or parse-failed content → `<ExtractionFailedPreview />`. Use these two rather than writing custom error UI.

## Props PreviewPane passes to your component

These flow from `DocumentPage` → `PreviewPane` → your component:

| Prop | Type | When to use |
|------|------|-------------|
| `docId` | `string` | Fetch full content via `getDocumentText(docId, ...)` for text-based viewers |
| `searchQuery` | `string \| null` | Current in-document search term; highlight matches |
| `searchActiveIndex` | `number` | Which match is active; scroll it into view |
| `onMatchCountChange` | `(count: number) => void` | Call this when you've counted matches |
| `imageZoom` | `number` | Current zoom level (25–400); for zoom-capable viewers |
| `onImageZoomChange` | `(z: number) => void` | User changed zoom; lift to DocumentPage |

Not every viewer needs all of these. TextPreview uses `docId` + search props; ImageViewer uses zoom props; PDF uses `onMatchCountChange`; MediaPreview uses none.

## State that lives in DocumentPage

Zoom state, search state, and mode state all live in `DocumentPage` and flow down through `DocumentToolbar` and `PreviewPane`. When adding a viewer with new toolbar controls, add props to `DocumentToolbar` and render them conditionally (`showImageControls={mime.startsWith('image/')}` style).

Do not manage zoom or search state inside the viewer component itself — that breaks DocumentToolbar's controls.

## A11y requirements

Every viewer component must have:
- `role="region"` with `aria-label` on the outermost container (e.g. `aria-label={`Code: ${title}`}`)
- Keyboard navigation for any interactive control
- `aria-label` on all icon-only buttons
- `aria-pressed` on toggle buttons (word-wrap, raw view, etc.)
- `aria-live="polite"` for status text the user needs to hear but that isn't focused (match counter, load progress)

## React-window v2 virtualization

Use react-window v2 when content exceeds thresholds (10K lines for text, 1K rows for tables). The v2 API is different from v1 — getting it wrong causes silent crashes or no-render:

```tsx
import { List } from 'react-window';

<List
  rowCount={lines.length}       // not itemCount
  rowHeight={22}                 // not itemSize
  height={containerHeight}
  width="100%"
  rowComponent={RowRenderer}     // not children
  rowProps={{}}                  // ← REQUIRED — v2 crashes with Object.values(null) if omitted
/>
```

For tables, react-window renders flat `div` children, so native `<table>` is impossible. Use ARIA role-table instead:

```tsx
<div role="table" aria-label="Data table">
  <div role="rowgroup">
    <div role="row">
      <div role="columnheader" aria-sort="none">Col A</div>
    </div>
  </div>
  <List rowComponent={({ index, style }) => (
    <div role="row" style={style}>
      <div role="cell">value</div>
    </div>
  )} rowProps={{}} ... />
</div>
```

Note: non-virtualized tables (<1K rows) should keep native `<table>` / `<thead>` / `<tbody>` for semantics.

## jsdom test setup

Viewer tests run in jsdom, which lacks real layout measurement. These mocks must exist in `src/test/setup.ts` before your tests will pass:

```ts
// Required by react-window v2 (ResizeObserver not in jsdom)
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Required by viewers that call scrollIntoView (search match scrolling)
Element.prototype.scrollIntoView = vi.fn();
```

For dialog/modal components:
```ts
HTMLDialogElement.prototype.showModal = vi.fn();
HTMLDialogElement.prototype.close = vi.fn();
Object.defineProperty(HTMLDialogElement.prototype, 'open', { writable: true, value: false });
```

PDF canvas: jsdom logs `"canvas.getContext not implemented"` — this is expected. Guard in the component (`if (!canvas.getContext('2d')) return;`) and do not suppress the warning in tests.

## Verification

```bash
npm run typecheck                                   # tsc --noEmit
npx vitest run src/features/documents/              # targeted viewer tests
```

Then manually verify in the running app:
- Content renders without console errors
- In-document search highlights matches and scrolls active match
- Zoom controls work (if applicable)
- UnsupportedPreview or ExtractionFailedPreview renders for error cases
- No visual regression in other MIME types (spot-check one)
