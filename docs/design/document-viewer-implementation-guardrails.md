# Document Viewer Implementation Guardrails

**Status:** Active guardrails  
**Parent issue:** #453  
**Design reference:** `docs/design/document-viewer-design.md`  

---

## Purpose

This file fixes and clarifies the document-viewer design package before implementation begins. It should be read together with `docs/design/document-viewer-design.md` and the implementation issues #440–#451.

The goal remains unchanged: build a fidelity-first document viewer that renders uploaded files as close as practical to the original file while preserving all existing Tomorrowland functionality.

---

## Issue Map

| Placeholder from design draft | Real GitHub issue | Title |
|---|---:|---|
| #A | #440 | Security: Sandbox HTML preview iframe |
| #B | #441 | Full document text API endpoint |
| #C | #442 | PDF.js viewer |
| #D | #443 | View mode switcher and fidelity status bar |
| #E | #444 | Image viewer with zoom/pan |
| #F | #445 | Metadata Details tab in InsightPane |
| #G | #446 | Server-side Office → PDF conversion pipeline |
| #H | #447 | Code/syntax viewer |
| #I | #448 | Media viewer |
| #J | #449 | In-document search and highlights |
| #K | #450 | Accessibility and performance hardening |
| #L | #451 | Document viewer test suite |

Do not use placeholder issue names in new implementation notes, PR descriptions, or agent missions. Use the real issue numbers above.

---

## Parent Tracking Issue

Use #453 as the parent issue for the whole document-viewer feature.

All implementation PRs should mention both:

1. The specific implementation issue, for example `Fixes #442`.
2. The parent tracking issue, for example `Part of #453`.

---

## Terminology Rules

Agents must keep these concepts separate:

| Term | Meaning |
|---|---|
| Original file | The raw source file bytes, available through download/open-original when the file still exists. |
| Rendered preview | Browser-native rendering of original bytes, for example PDF.js for PDFs, `<img>` for images, native `<audio>`/`<video>` for media. |
| Converted preview | Server-generated preview for formats the browser cannot render directly, for example LibreOffice-generated PDF for DOCX/PPTX/XLSX. |
| Extracted text | Text extracted from the source file by the ingestion/extraction pipeline. |
| Translation | Translated extracted text, either fast or high-quality. |
| Metadata | File/source/processing/version details. |

Do not imply that DOCX, PPTX, XLSX, ODT, ODS, or ODP are rendered as raw originals in-browser. For those formats, the UI should offer download/open-original plus converted preview or extracted text fallback.

---

## Correct MVP Order

Recommended MVP implementation order:

1. #440 — HTML sandbox security fix. Target `main` directly.
2. #441 — Full document text API.
3. #442 — PDF.js viewer.
4. #443 — View mode switcher and fidelity status bar.
5. #444 — Image viewer with zoom/pan.
6. #445 — Metadata Details tab.

This MVP delivers the biggest user-visible improvement with the least architectural risk.

---

## Post-MVP / Parallel Tracks

These are valuable, but should not block the first viewer MVP:

- #447 — Code/syntax viewer.
- #448 — Media viewer.
- #449 — In-document search.
- #450 — Accessibility and performance hardening.
- #451 — Final test suite/gap analysis.
- #446 — Office → PDF conversion. Treat this as a high-risk integration track because it touches Docker, DB schema, backend jobs, storage, API, frontend, and tests.

---

## TIFF Policy

The design matrix mentions server-side TIFF → PNG/WEBP conversion as a possible high-fidelity future enhancement. That is **not** part of the MVP image viewer.

For #444:

- TIFF is fallback-only.
- If the browser cannot render TIFF, show `UnsupportedPreview` with download/open-original.
- Do not implement client-side TIFF transcoding.
- Do not implement server-side TIFF conversion in #444.

Future TIFF conversion can be designed as a separate post-MVP issue.

---

## Office Conversion Policy

#446 is important for high-fidelity Office previews, but it should not block #441–#445.

Rules:

- Use #446 only after the base viewer shell is stable, or run it as a separate sub-branch under `feature/document-viewer/office-conversion`.
- Keep extracted text fallback working for Office documents at all times.
- If converted preview generation fails, the viewer must remain usable through extracted text and download/open-original.
- Do not introduce cloud conversion services unless explicitly approved.

---

## Branching

- #440 targets `main`.
- #441–#451 target `feature/document-viewer`.
- #446 should use a sub-branch, recommended: `feature/document-viewer/office-conversion`.

---

## Agent Execution Notes

Before starting any issue, agents should read:

- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `docs/agents/coding-behavior.md`
- `docs/design/document-viewer-design.md`
- this file
- the specific issue body

Agents should not read `spec.md` or `spec-v4.pdf` unless the issue explicitly says so.
