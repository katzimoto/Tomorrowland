# Tomorrowland Web — UI Kit

A high-fidelity, click-through recreation of the operator workspace at
`frontend/` in the source repo. Boots into the **Search** page (post-login)
with the corpus of mock documents in `data.js`; every interaction below
works against that in-memory data — no network calls.

## What's wired up

| Surface | Where | Interactions |
|---|---|---|
| **Sign in** | accessible via Sign out in the nav rail | Email + password fields, language picker, validation error styles. Submit re-enters the app. |
| **Search** | default route | Free-text query, three search modes (Hybrid · Keyword · Semantic), filter panel with file-type / source / translation checkboxes, removable filter chips, result rows with hover + selected states. |
| **Quick preview dialog** | "Preview" button on any row | Dialog with the modal shadow, snippet, source meta, "Open document" and "Close preview" actions. |
| **Document viewer** | click any result | Toolbar with source + tags badge cluster, "Chat about this" + "Download" actions, paper preview pane, insight tabs (Summary, Q&A, Related, Annotations, Comments, Versions). |
| **Chat** | nav rail or "Chat about this" | Sidebar of past chats, scope bar when scoped to a doc, starter prompt pills, message bubbles with grounded-source citations, autosizing composer, Enter-to-send, Shift+Enter for newline. |
| **Nav rail** | left of every screen | Collapsed (72px) by default; toggle expands to 220px. Notifications badge. Sign out flow triggers an "expired" banner on the next sign-in. |

## File layout

```
ui_kits/tomorrowland-web/
├── index.html        — boots React+Babel, loads everything in order
├── styles.css        — application-level layout & component styles
├── data.js           — mock corpus (5 docs, 4 chat sessions, starters)
├── Icons.jsx         — inline Lucide-shaped SVG set
├── Primitives.jsx    — Button, Badge, TextInput, SearchInput
├── NavRail.jsx       — left sidebar with collapse/expand
├── SignIn.jsx        — Login card
├── SearchView.jsx    — Search page, filter panel, result rows, preview dialog
├── DocumentView.jsx  — Document viewer with insight tabs
├── ChatView.jsx      — Chat sidebar + stream + composer
└── App.jsx           — top-level view switch & sign-in gate
```

Every file is intentionally small (<300 lines) so you can copy a single
component into a new project without unwinding a framework. All styles are
plain CSS scoped to class names — no CSS modules, no PostCSS — and the
tokens come from the project-root `colors_and_type.css`.

## Provenance

Recreated from the production codebase:

- `frontend/src/components/layout/NavRail.tsx` → `NavRail.jsx`
- `frontend/src/components/primitives/{Button,Badge,TextInput,SearchInput}.tsx`
  → `Primitives.jsx`
- `frontend/src/features/auth/LoginPage.tsx` → `SignIn.jsx`
- `frontend/src/features/search/{SearchPage,ResultRow,FilterPanel}.tsx`
  → `SearchView.jsx`
- `frontend/src/features/documents/{DocumentPage,DocumentToolbar,InsightPane}.tsx`
  → `DocumentView.jsx`
- `frontend/src/features/chat/{ChatPage,ChatSidebar,ChatWindow,ChatInput,MessageBubble,ChatCitationCard,StarterQuestions}.tsx`
  → `ChatView.jsx`
- English copy lifted verbatim from `frontend/src/i18n/locales/en.ts`

Behaviour is intentionally cosmetic — the backend services (Meilisearch,
Qdrant, Ollama, LibreTranslate, Kafka) are not stubbed. If you need to
prototype a real flow, drop the existing API client in and replace the
mock `data.js`.
