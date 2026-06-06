---
name: tomorrowland-design
description: Use this skill to generate well-branded interfaces and assets for Tomorrowland, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping a dark-first, operator-grade document intelligence workspace.
user-invocable: true
---

# Tomorrowland design

Tomorrowland is a local-first, air-gapped document intelligence platform —
a private search workspace over files, email, Confluence, and Jira with
hybrid keyword + vector retrieval, document preview, and optional on-prem
LLM Q&A. The visual language is **dark-first, infrastructural, terse**:
think GitHub-on-prem more than Notion.

## Where to start

Read **`README.md`** at the root of this skill first. It is the single
source of truth for:

- The product surface map (Sign in, Search, Document, Chat, Admin).
- Tone and copy rules — terse, imperative, no emoji, no marketing voice.
- Color, type, spacing, shape, motion, focus, layout tokens.
- Iconography (Lucide, stroke 1.5, three sizes).

Then open **`colors_and_type.css`** — this is the only stylesheet you need
to import to get the Tomorrowland look. Every token is a CSS variable
under a `--tl-*` or semantic name (`--color-bg`, `--color-primary`, etc).

For high-fidelity composition, study **`ui_kits/tomorrowland-web/`**. The
recreated React components (`Primitives.jsx`, `NavRail.jsx`,
`SearchView.jsx`, `DocumentView.jsx`, `ChatView.jsx`) are small and
self-contained — copy a component, swap the data, and you have a real
Tomorrowland screen.

The **`preview/`** directory contains per-token cards (palette, type,
spacing, components). Use them as a visual reference, not as a source
of truth — the truth is `colors_and_type.css` and the UI-kit components.

## When you create

- **Visual artifacts (slides, mocks, throwaway prototypes):** copy the
  needed assets from `assets/` out into your output (logo.svg or
  favicon.svg, the Lucide icon shapes you need). Link
  `../colors_and_type.css`. Write static HTML. Do not invent colors —
  every hex should come from the token file.
- **Production code:** install Lucide React, copy `colors_and_type.css`'s
  tokens into your tokens file, and rebuild components by mirroring the
  files under `ui_kits/tomorrowland-web/`. The JSX recreations there are
  cosmetic but accurate.

## Brand rules you must respect

- **Dark only.** There is no light mode. Backgrounds are flat `#0d1117`,
  surfaces are `#161b22`, borders are the single `#30363d`. No
  gradients in chrome.
- **Two color systems, never mixed.** Azure blue `#58a6ff` for UI;
  cyber cyan `#00e5ff` for the logo only. Putting cyan in a button reads
  as a different product.
- **No emoji.** Anywhere in product copy. The only non-ASCII characters
  are `·`, `…`, and curly quotes inside sentences.
- **Five-step type scale only.** Page 24 / section 18 / panel 14 / body
  14 / meta 12. Don't add a sixth.
- **Two radii.** `--radius-panel: 6px` for buttons/cards/inputs/dialogs;
  `--radius-chip: 4px` for badges and segmented toggles. Pills exist in
  exactly two places (chat starter prompts, active filter chips).
- **Lucide icons, stroke 1.5.** Don't invent SVG glyphs.

## Tone fingerprint

Terse, imperative, infrastructural. Mirror the verbatim copy in
`README.md`'s Content Fundamentals section. Buttons say "Sign in", "Add
Source", "Retry" — never "Get started" or "Let's go". Empty states are
two lines: what's missing, what would change it. Errors name the
component that failed.

## When invoked without specifics

If the user invokes this skill with no other guidance, ask them what
they want to build or design. Useful questions:

- What surface — extend the existing product, add a new internal admin
  screen, or build something off-product (marketing, slide deck, doc)?
- Static HTML output or production React?
- Do they have real content, or should you use the mock corpus in
  `ui_kits/tomorrowland-web/data.js`?

Then act as an expert designer who outputs HTML artifacts or production
code, depending on the need.
