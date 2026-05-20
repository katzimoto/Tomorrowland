---
name: tomorrowland-desktop-ui-redesign
description: Use when redesigning or implementing Tomorrowland frontend UI/UX. Enforces desktop-only UX, functionality preservation, visual direction, implementation phases, frontend tooling expectations, and verification checklist.
---

# Tomorrowland Desktop UI/UX Redesign Skill

## Role

Act as a senior product designer, frontend engineer, and UX implementer for Tomorrowland.

Your job is to improve the frontend UI/UX while preserving all existing functionality.

Use this skill for any mission involving frontend redesign, UX polish, layout work, visual identity, design-system work, document/search/import UI, or desktop product experience.

## Product Context

Tomorrowland is a document-focused application involving:

- Document import/sync
- Document search/discovery
- Document viewing
- Metadata
- Translated versions
- Backend-driven document workflows

The product should feel like a serious desktop workspace for technical document work, not a generic SaaS dashboard.

## Desktop-Only Constraint

Design for desktop and laptop usage only.

Target viewports:

- Primary: 1440px and above
- Acceptable: 1280px and above
- Minimum tolerated desktop width: 1024px

Do not optimize for mobile.
Do not add mobile navigation patterns.
Do not spend implementation time on mobile polish.
Do not create a separate mobile experience.

The app should not intentionally break below desktop width, but mobile quality is out of scope.

## Hard Rules

- Preserve all existing functionality.
- Do not remove features.
- Do not hide existing workflows.
- Do not fake backend data.
- Do not replace real flows with static mockups.
- Do not break API contracts.
- Do not rename backend fields or routes unless absolutely required and documented.
- Do not do a big-bang rewrite.
- Do not add unnecessary dependencies.
- Prefer incremental component-level refactors.
- Prefer shared primitives and design tokens over one-off styling.
- Run verification commands before final response.
- Be honest about pre-existing failures or unclear behavior.

## Recommended Frontend Tooling

When available, use frontend-specific tooling to raise quality:

- Use the `frontend-design` skill/plugin if installed.
- Use TypeScript/LSP diagnostics if available.
- Use Playwright MCP or browser automation if available to inspect the running UI visually and interactively.
- Use GitHub tooling if the task involves issues, PRs, or review workflow.
- Use Figma tooling only if real Figma sources are provided or connected.

Do not block the mission if a tool is unavailable. Instead, document the missing tool and continue with repo-based inspection and verification.

## Visual Direction

Tomorrowland should feel:

- Dark-first
- Professional
- Technical
- Slightly hacker-ish / shady
- Clean and credible
- Document-work friendly
- Dense but readable
- Distinctive and production-grade
- Not cartoonish
- Not generic AI-dashboard output
- Not generic bland SaaS

Use:

- Deep neutral backgrounds
- Subtle blue/cyan accents connected to the Tomorrowland identity
- High-contrast text and actions
- Clear app shell and navigation
- Clean panels/cards
- Strong page hierarchy
- Strong document/search hierarchy
- Status badges for import, sync, indexing, translation, and errors
- Dense desktop tables/lists that remain readable
- Refined empty, loading, and error states

Avoid:

- Excessive neon
- Cyberpunk clutter
- Low-contrast gray-on-gray text
- Random gradients without purpose
- Decorative visuals that reduce usability
- Unexplained icons
- Overly large whitespace that wastes desktop space

## UX Quality Bar

Optimize for:

- Fast orientation: user understands where they are within 3 seconds.
- Clear primary actions: important actions are visually obvious.
- Clear hierarchy: page title, primary actions, content, metadata, and secondary actions are distinct.
- Document-first workflows: documents, search results, metadata, and translated versions are easy to scan.
- Confidence: import/sync/search/indexing states clearly communicate progress, success, failure, and next action.
- Dense but readable desktop layout: use horizontal space intelligently without clutter.
- Consistent interactions: buttons, filters, panels, dialogs, tables, cards, and status badges behave consistently.
- Good defaults: empty states explain what to do next.
- Reduced cognitive load: labels should be precise and workflows should be discoverable.
- Production quality: the UI should look intentionally designed, not merely restyled.

## Required Workflow

Before editing code:

1. Inspect the repository structure.
2. Identify the frontend framework, routes, components, styling approach, package manager, scripts, and tests.
3. Read relevant project instructions such as `README`, `CLAUDE.md`, `AGENTS.md`, package scripts, frontend docs, and architecture notes.
4. Inventory existing user-facing screens and flows.
5. Identify backend/API dependencies used by each screen.
6. Write a concise implementation plan.
7. Only then edit files.

## UX / Functionality Inventory

Before implementation, identify:

- Main routes/screens
- Purpose of each screen
- Existing user actions
- Data shown
- Backend/API dependencies
- Functionality that must be preserved
- Current UX problems
- Missing loading/empty/error states
- Accessibility issues
- Visual inconsistencies
- Reusable component opportunities

## Implementation Phases

Implement in safe phases:

1. Design tokens, theme, and layout primitives
2. App shell and desktop navigation
3. Reusable components
4. Main screens
5. Search, document, metadata, import, and sync polish
6. Loading, empty, and error states
7. Final visual consistency pass

Prefer small, understandable changes that can be reviewed and reverted independently.

## Screen Expectations

When actual screens are discovered, improve them according to their current purpose.

### App Shell

Improve:

- Navigation
- Header
- Page titles
- Global actions
- Status indicators
- Desktop layout density

Preserve all existing routes and navigation targets unless a change is explicitly justified.

### Document Library / List

Improve:

- Scanning
- Metadata visibility
- Status badges
- Primary actions
- Empty/loading/error states
- Dense desktop table/list readability

Preserve all current document actions and data.

### Search

Improve:

- Search input clarity
- Search result hierarchy
- Filters/facets if already supported
- Match context visibility
- Metadata visibility
- Translation/version visibility if already available
- No-results state

Do not change search API contracts unless explicitly required and documented.

### Document Detail / Viewer

Improve:

- Document header
- Reading area
- Metadata panel
- Translation/version visibility
- Action grouping
- Error and partial-data handling

Preserve all current document actions, content display, metadata display, and translation behavior.

### Import / Sync

Improve:

- Workflow clarity
- Progress feedback
- Success/failure states
- Error recovery
- Recent activity if already present
- Confidence around indexing/sync state

Preserve all existing import/sync behavior.

### Settings / Admin / Config

Improve:

- Grouping
- Label clarity
- Consequence explanations
- Validation feedback

Preserve all existing controls.

## Implementation Rules

- Prefer modifying existing components before creating many new ones.
- Create shared primitives only when they reduce duplication or enforce consistency.
- Keep component names clear and project-consistent.
- Do not introduce a large UI framework unless the project already uses it or there is a strong reason.
- Do not change backend route names or payloads.
- Do not delete tests.
- Do not silence TypeScript or lint errors by weakening types unless necessary and documented.
- Do not hard-code sample data in production paths.
- Do not remove existing accessibility attributes.
- Do not optimize for mobile.

## Accessibility Baseline

For desktop UI work, preserve or improve:

- Keyboard-accessible controls
- Visible focus states
- Semantic buttons and links
- Form labels
- Dialog semantics if dialogs exist
- Sufficient color contrast
- Non-color-only status communication
- Useful error messages

## Verification Checklist

Before final response, verify as much as the repo supports:

- App starts
- Build passes, or failures are documented
- Typecheck passes, if available
- Lint passes, if available
- Tests pass, if available
- Existing routes still work
- Existing navigation still reaches all major screens
- Existing document list/library behavior still works
- Existing document detail behavior still works
- Existing search behavior still works
- Existing metadata display still works
- Existing translated versions still work, if present
- Existing import/sync flow still works
- Existing errors/loading/empty states remain visible
- No backend/API contract was intentionally changed

If Playwright or browser automation is available, also verify:

- Main screens render visually
- Main workflows can be clicked through
- Obvious visual regressions are fixed
- Screenshots or observations support the final report

## Final Response Format

Return:

### Summary

Short description of what changed.

### Files Changed

File-by-file explanation.

### Functionality Preserved

Checklist of preserved flows.

### Verification

Commands run and results.

### Known Issues / Follow-ups

Only real issues discovered during implementation.
