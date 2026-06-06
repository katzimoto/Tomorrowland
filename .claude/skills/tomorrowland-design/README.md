# Tomorrowland Design System

> A local-first knowledge intelligence platform for private document corpora.
> Operator-grade, dark-first, air-gap friendly.

This design system documents the visual language, content style, and UI
primitives behind **Tomorrowland** — a Docker Compose application that indexes
files, email, Confluence, and Jira into a private hybrid keyword + vector
search workspace with previews, translation, comments, and optional
on-prem LLM Q&A. It runs without runtime internet access when installed from
the air-gapped release artifacts.

The aesthetic is deliberately infrastructural: this is a tool for IT and
knowledge ops, not a consumer product. Think GitHub-on-prem more than Notion.

## Sources

> **Reconciled to `main` on 2026-06-06.** Installed as the repo skill
> `.claude/skills/tomorrowland-design/`. Text-secondary/muted hexes were
> updated to the current WCAG 2 AA values (`#b1bac4` / `#9da7b3`) and the
> surface map was extended with the live secondary routes. The non-indexed
> `export/`, `scraps/`, and `previews-office/` folders from the original zip
> were dropped; pull them from the source archive if needed.

Pulled from the production codebase:

- **GitHub:** [github.com/katzimoto/Tomorrowland](https://github.com/katzimoto/Tomorrowland) (`main`)
  - Design tokens — `frontend/src/styles/tokens.css`
  - Primitives — `frontend/src/components/primitives/`
  - Layout / nav — `frontend/src/components/layout/`
  - Pages — `frontend/src/features/{auth,search,documents,chat,admin}/`
  - English copy reference — `frontend/src/i18n/locales/en.ts`
  - Spec / product surface map — `spec.md`, `spec-v4.pdf`
  - Brand assets — `frontend/public/{favicon.svg, tomorrowland-logo-cyber-bike.svg, icons.svg}`

You can explore the repo further to extend this system — every component CSS
module is named after its rendered component and is short enough to read in
one sitting.

---

## Index

| File / folder | What's in it |
|---|---|
| `colors_and_type.css` | All design tokens — palette, type scale, spacing, radii, shadows, focus rings. Import this and you get the look. |
| `assets/logo.svg` | The "cyber-bike" mark — full neon version with grid, scanlines, soft glow. |
| `assets/favicon.svg` | Simplified mark — no grid, no scanlines. Use this anywhere ≤ 32px. |
| `assets/icons-social.svg` | SVG `<symbol>` sprite — GitHub, X, Bluesky, Discord, plus two stroked utility marks. Reference via `<use href="...">`. |
| `fonts/` | Empty, with a README explaining the Inter substitution. See [Type](#type) below. |
| `SKILL.md` | The agent-invocable summary. Identical schema works in this app and in Claude Code skills. |
| `frontend/` | A read-only snapshot of the imported source files. Treat as reference, not as the system. |
| `preview/` | Per-token cards rendered for the Design System tab. Not for production use. |
| `ui_kits/tomorrowland-web/` | High-fidelity recreations of the four core surfaces: Sign in, Search, Document, Chat. |
| `SKILL.md` | The agent-invocable summary — drop the whole folder into a Claude Code skill and ask it to design with Tomorrowland's brand. |

---

## Product Context

Tomorrowland is a **single product** delivered as a Compose stack:

| Surface | Purpose |
|---|---|
| **Sign in** | Local + LDAP auth. Internal-tool feel; left-aligned card, no marketing. |
| **Search** | The home page. Hybrid (keyword + semantic) over the indexed corpus, filter panel on the left, result rows with source / tags / version / translation badges. |
| **Document viewer** | Preview pane + right-side insight panel (Summary, Q&A, Related, Annotations, Comments, Versions). |
| **Chat** | RAG Q&A grounded in accessible documents. Sidebar of past chats, scoped to a doc / source / search result. |
| **Admin** | Source management (folder, SMB, Confluence, Jira, Kafka). Tabular, dense, sysadmin-shaped. |

The five surfaces above are the primary workspace. The live product also ships
secondary, feature-flagged routes that reuse the same shell, primitives, and
tokens — design them with the identical language, no new patterns:

| Secondary surface | Purpose |
|---|---|
| **History** | Personal search + read history. |
| **Notifications** | Unread subscription alerts. |
| **Subscriptions** | Manage topic/alert subscriptions and thresholds. |
| **Expertise** | Expertise-map browser (who reads what, by topic). |
| **Annotations / Comments** | Surfaced inside the document viewer's insight panel, not as standalone routes. |

There is no marketing site, no mobile app, no second product. Everything in
this design system targets the operator workspace.

---

## Content Fundamentals

The voice is **terse, technical, and trustworthy** — the way a competent
sysadmin writes a runbook. There is no marketing language, no exclamation
points, no emoji in the product copy. Where most consumer apps would
encourage, Tomorrowland states.

### Tone reference

| Trait | How it shows up |
|---|---|
| **Person** | Mostly imperative ("Sign in", "Add Source", "Try again"). When addressing the user, "you" — never "we" or "I". The system never refers to itself. |
| **Case** | Sentence case for headings ("Sign in to Tomorrowland", "No sources yet"). Title case for primary action buttons ("Add Source", "Save Source") in admin only. Buttons elsewhere are sentence case ("Sign in", "Send"). |
| **Length** | Headings are short and literal. Body text is one or two sentences. Empty states get a one-line title and a one-line body. |
| **Emoji** | None. Never. The only "decorative" element in copy is the middle dot · used as a separator in metadata rows (`PDF · 2.3 MB · 4d ago`). |
| **Errors** | Name the system that failed and what to do. "The search backend is not reachable. Check the server and try again." Never "Oops!" or "Something's wrong." |
| **Empties** | Two lines: what's missing, what would change it. "No notifications" / "You'll be notified here when documents match your subscriptions." |
| **Loading** | A single ellipsis: `Loading…` or `Loading evidence…`. No spinners with text below them unless the operation can fail. |

### Examples lifted verbatim

```
Sign in to Tomorrowland
Your session expired. Sign in again.

Search unavailable
The search backend is not reachable. Check the server and try again.

No results found
No accessible documents match your query. Try different terms or remove filters.

Use ↑/↓ or j/k to choose a result, Enter to open, Space to preview, and Esc to close preview.

Based only on documents you can access.

Sync completed. Indexed 142 documents. Skipped 3. Failed 0.
```

The keyboard hint above is characteristic: a real keyboard shortcut listed
inline in body text, no fanfare. Tomorrowland assumes its users are at a
keyboard with both hands on it.

### Naming

- The product is **Tomorrowland**, lowercase only when it appears mid-sentence
  inside code paths or filenames (`tomorrowland-airgap.sh`). Everywhere
  user-facing it is title-cased: "Sign in to Tomorrowland".
- A historical alias **Neverland** appears in old release artifact names — do
  not surface this anywhere new.

---

## Visual Foundations

### Mode

**Dark-first.** There is no light mode. `<html>` sets `color-scheme: dark`
and the entire palette is built for a dark workspace background — borders are
near-black, badges are 15%-tinted versions of their action color, shadows
have heavy alpha. If you need a light surface, you are off-brand.

### Color

| Role | Token | Hex | Use |
|---|---|---|---|
| Page background | `--color-bg` | `#0d1117` | The body. The default behind everything. |
| Surface | `--color-surface` | `#161b22` | Cards, header bar, nav rail, login card. |
| Surface raised | `--color-surface-raised` | `#1c2128` | Tooltips, popovers, active mode button, hovered rows. |
| Border | `--color-border` | `#30363d` | Every divider. Never tinted — this is the only line color. |
| Text primary | `--color-text-primary` | `#e6edf3` | Body, titles, input values. |
| Text secondary | `--color-text-secondary` | `#b1bac4` | Field labels, snippets, secondary nav. Lightened to meet WCAG 2 AA (4.5:1) on raised surfaces. |
| Text muted | `--color-text-muted` | `#9da7b3` | Timestamps, helper text, placeholder. AA-compliant on every dark surface. |
| Primary | `--color-primary` | `#58a6ff` | Buttons, links, active tab/route, focus ring. Azure blue, not the brand cyan. |
| Success / tag | `--color-success` | `#3fb950` | Tag badges, success states. |
| Warning / translation | `--color-warning` | `#d29922` | Translation badges, session-expired banners. |
| Danger | `--color-danger` | `#f85149` | Destructive buttons, error text, validation. |
| Brand cyber cyan | `--tl-cyber-cyan` | `#00e5ff` | Logo only. Never in chrome. |

**Two color systems coexist:** the dark workspace (azure blue) for product
chrome, and the neon cyan for the logo mark. Don't mix them — `#00e5ff` in a
button reads as a different product.

Badges are the only place color earns its keep. Each variant is a `15%` tint
of its hue as background with the full hue as text — `source` (blue), `tag`
(green), `translation` (amber), `success/warning/danger`. Neutral is
`rgba(255,255,255,0.07)`.

### Type

- **Family:** Inter, with the full system fallback stack. Mono is JetBrains
  Mono (for `<code>`, debug query text). No display face.
- **Substitution flag:** the production code does **not** ship Inter as a
  webfont — it relies on the system stack. This design system loads Inter
  from Google Fonts so the look is consistent across machines that don't
  have Inter installed. **If you have a brand-licensed Inter Variable
  woff2, please drop it in `fonts/` and replace the `@import` at the top of
  `colors_and_type.css`.**
- **Scale:** five steps only — page title (24/32/600), section (18/26/600),
  panel/h3 (14/20/600), body (14/20/400), meta (12/16/500). Don't invent a
  sixth.
- Headings are sentence case. Body line-height is `20px` against `14px` size
  — tight, deliberately information-dense.

### Spacing

- 4px base unit, named `--space-1` … `--space-14`. Every padding, gap, and
  margin in the system snaps to this.
- Page padding is `24px` desktop, `16px` mobile. Toolbar/header padding
  matches.
- Component gaps default to `--space-2` (8) for inline groups and
  `--space-3` (12) for stacked controls.

### Shape

- **Two radii only.** `--radius-panel: 6px` (cards, buttons, inputs, dialogs,
  toasts, the nav rail items). `--radius-chip: 4px` (badges, segmented mode
  toggle, filter selects).
- `--radius-pill: 999px` is permitted in exactly two places: chat starter
  suggestions and the active-filter chips in the search header. Resist using
  it elsewhere — pills are not the system's default rounded shape.

### Borders, dividers, fills

- One border color, full-stop: `#30363d`. No tinted borders, no rainbow
  alert boxes. A "warning" surface gets a 30%-alpha amber border, but the
  default `--color-border` is never overridden in a panel.
- Cards do not lift off the background with shadow — they sit flat with a
  1px border. Shadows are reserved for popovers and modals.
- Active-row treatment is `background: var(--color-surface-raised)` plus
  `outline: 2px solid var(--color-primary); outline-offset: -2px;` — never a
  left-border accent stripe.

### Backgrounds & imagery

- **No hero photography.** Nothing in the product uses bitmap imagery —
  documents are previewed, but no decorative photos exist.
- **No gradients in chrome.** Backgrounds are flat. The login page is a flat
  `#0d1117`. The only gradient is the soft Gaussian neon glow on the brand
  mark itself (SVG filter).
- The brand mark's own background is `#060c1a` (deeper than the app bg)
  with a faint 10px cyan grid and 4-step scanlines — these are decorative
  elements of the *logo*, not the *UI*. Do not bring them into product
  chrome.

### Shadows & elevation

```css
--shadow-menu:  0 4px 16px rgba(0,0,0,0.50), 0 1px 4px rgba(0,0,0,0.30);
--shadow-modal: 0 8px 48px rgba(0,0,0,0.70), 0 2px 12px rgba(0,0,0,0.40);
```

Two levels. Menus and dialogs only. Buttons, cards, inputs do not lift.

### Focus

A double-stroked focus ring: 2px of `--color-bg` inside, then 2px of
`--color-primary` outside. Survives on every surface, including the same
azure-blue primary buttons (because the inner ring acts as a knockout).

```css
--focus-ring: 0 0 0 2px var(--color-bg), 0 0 0 4px var(--color-primary);
```

`:focus-visible` is the default — keyboard focus only, no ring on mouse
clicks.

### Motion

- `120ms ease` on color / background / border transitions. Every interactive
  primitive (buttons, rows, tabs, nav items) uses this exact duration.
- `180ms ease` for the nav rail width transition (collapsed ↔ expanded).
- `350ms` debounce on the search input — type, pause, results refresh.
- No spring physics, no bounces, no entrance animations. The skeleton loaders
  shimmer at the default browser rate. The button spinner is a `600ms`
  linear rotation.

### Hover & press

- **Buttons** darken on hover via a paired hover-color token
  (`--color-primary-hover`, `--color-danger-hover`), not opacity.
- **Rows and list items** swap from `--color-surface` to
  `--color-surface-raised`. Same hue family, one step lighter.
- **Ghost buttons** add the page-background as a hover surface and brighten
  the text from secondary to primary.
- **No press states** that shrink, dim, or translate. The system relies on
  the focus ring for active-input feedback. If you find yourself reaching
  for `transform: scale(0.98)` on press, stop.

### Transparency & blur

- Used sparingly. The modal backdrop is `rgba(0,0,0,0.65)` with
  `backdrop-filter: blur(2px)` — that's the entire blur budget.
- Badge backgrounds use 15% alpha tints (see Color). Active filter chips on
  the search header sit on a 100%-opaque surface.
- Glass / frosted backgrounds are off-brand.

### Layout rules

- **Sticky nav rail** on the left (72px collapsed, 220px expanded). On
  mobile, it becomes a 5-tab bottom bar.
- **Sticky page header** at the top of every page (search header, document
  toolbar, chat page title). Same surface color as the nav rail.
- **Filter / sidebar panels** are 280px wide, fixed, scroll independently
  from the main content.
- **Insight panel** (right side of document viewer) is `flex: 2` of the
  remaining width with `min-width: 300px; max-width: 480px`.
- Page content has a `max-width: 1200px` constraint on result lists; other
  panels fill their column.

### Cards

A "card" is `--color-surface` with a 1px `--color-border`, `--radius-panel`
corners, and no shadow. Padding is `--space-6` (24) for primary cards
(login, dialog body) and `--space-4` (16) for secondary ones (citation
cards, source rows). That's the entire card system.

---

## Iconography

**Primary icon set: [Lucide](https://lucide.dev) (`lucide-react`)** — every
chrome icon in the production app is a Lucide glyph, imported by name. The
production code uses these specifically; if you need a new icon, take it
from Lucide first:

```
Search, MessagesSquare, Bell, History, Bookmark, Shield, Network,
ChevronLeft, ChevronRight, ChevronDown, LogOut, X, Eye, Info,
FileText, Image, Archive, Mail, File, Download, Plus, Trash2, Edit2
```

Stroke `1.5`, size `20px` for nav rail and primary actions, `18px` for row
icons, `14px` for inline meta. Color inherits from `currentColor`.

This design system links Lucide from a CDN — no local sprite. See any UI
kit HTML for the loader:

```html
<script src="https://unpkg.com/lucide@0.511.0/dist/umd/lucide.js"></script>
<i data-lucide="search"></i>
<script>lucide.createIcons();</script>
```

**Social glyph sprite:** `assets/icons-social.svg` carries five `<symbol>`s
— `bluesky-icon`, `discord-icon`, `documentation-icon`, `github-icon`,
`social-icon`, `x-icon`. The two stroked symbols use the brand purple
`#aa3bff` from an older marketing site and are not used anywhere in the
product chrome — they're preserved here in case the source repo grows a
public landing page. Reference via `<use href="icons-social.svg#github-icon">`.

**Emoji and unicode:** none. The product never uses emoji as icons. The only
non-ASCII characters in copy are the middle dot `·` (used in metadata rows),
the ellipsis `…`, and curly quotes inside body sentences. Status text uses
words ("Active", "Paused", "Success", "Failed"), not colored dots — color
comes from the surrounding badge.

**Logo:** `assets/logo.svg` for any context bigger than `32px` (it includes
a faint cyan grid + scanlines + soft glow). `assets/favicon.svg` is the
simplified mark — same paths, no grid, no scanlines — and is what you want
at favicon and nav-rail sizes.

---

## Building with this system

```html
<link rel="stylesheet" href="colors_and_type.css">
<link rel="icon" href="assets/favicon.svg">

<!-- Lucide (icons) -->
<script src="https://unpkg.com/lucide@0.511.0/dist/umd/lucide.js"></script>
```

Then write normal HTML with the tokens — see `ui_kits/tomorrowland-web/` for
fully wired examples (sign in, search, document viewer, chat).

---

## Caveats

- **Inter is substituted** from Google Fonts — production runs on the
  system Inter stack. Ship a real Inter Variable woff2 when you have one.
- **No marketing surface exists**, so this system has no hero, no pricing,
  no testimonial typography. If you need a marketing site, you'll be
  designing net-new on top of these foundations.
- The brand cyan `#00e5ff` lives in the logo only. Don't graft it onto UI.
