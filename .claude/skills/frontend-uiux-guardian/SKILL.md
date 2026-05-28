---
name: frontend-uiux-guardian
description: Use for Tomorrowland frontend UI/UX redesign, visual polish, layout cleanup, empty/error/loading states, and UX consistency work while preserving existing functionality.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: frontend-agents
---

# Frontend UI/UX Guardian

## Scope

This skill covers targeted UI/UX improvements: loading states, empty states, label clarity, component-level polish, and visual consistency — without structural redesign.

For full-scale redesign involving design system foundations, visual identity overhaul, or phase-by-phase restructuring, use `tomorrowland-desktop-ui-redesign` instead.

## Core rule

Improve the interface without changing the product contract. Preserve existing functionality, API usage, permissions, navigation, and data flow unless the mission explicitly says otherwise.

## Before changing UI

Identify:

- The exact screen or component.
- The existing user flow to preserve.
- Data dependencies and API contracts.
- Loading, empty, error, and success states.
- Accessibility and responsive behavior expectations.

## Allowed improvements

- Layout, spacing, hierarchy, readability, and visual consistency.
- Clearer labels, helper text, and action affordances.
- Better loading, empty, and error states.
- Reduced clutter while preserving access to existing actions.
- Tomorrowland branding alignment.

## Forbidden by default

- Removing features or actions.
- Changing API contracts.
- Replacing routing patterns.
- Hiding errors without recovery guidance.
- Rewriting unrelated screens.
- Broad design-system rewrites unless explicitly requested.

## Verification

Use the smallest relevant checks:

- Typecheck or frontend build when available.
- Focused component tests when practical.
- Manual flow notes for import, search, document preview, translation, and settings where relevant.
- Screenshots or before/after notes for visual changes.

## Handoff

Report changed components, preserved flows, changed UX behavior, verification, skipped checks, and remaining risk.
