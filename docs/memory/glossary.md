# Tomorrowland Glossary

Shared vocabulary for agents. Add terms only when they prevent repeated confusion.

## Product terms

- Document: The core item Tomorrowland indexes, previews, translates, and searches.
- Workspace: A project boundary for document workflows.
- Metadata: Structured document attributes used for filtering, ranking, display, and search.
- Translated variant: A translated text representation tracked separately from original text.
- Preview: User-visible rendering or snippet of document content.
- Document Chat: Persistent, scoped conversational Q&A over documents. Multiple sessions per user; each session has a scope type and ordered messages with citations. Route: `/chat`.
- Chat Session: A named conversation thread with a `scope_type`, `scope_ids`, and a list of `ChatMessage` records. Sessions persist across page reloads.
- Chat Scope: The document set a chat session operates over. Types: `all_accessible_documents`, `single_document`, `selected_documents`, `source`, `folder`, `current_search_results`.
- Citation: A grounded reference attached to an assistant message, linking a claim to a specific document chunk. Key fields: `citation_id` (stable UUID), `document_id`, `doc_title`/`document_title`, `chunk_text`/`text_excerpt`, `score`, `chunk_index`.

## System terms

- API: FastAPI service for product routes and service orchestration.
- Frontend: React UI for import, search, preview, translation, settings, and workspace flows.
- Worker: Background process for extraction, indexing, translation, sync, or packaging jobs.
- Search index: Keyword or full-text index over document content, metadata, and translated variants.
- Vector store: Embedding-backed retrieval layer.
- Local model runtime: Optional local LLM service.

## Agent terms

- Mission: A scoped task brief with goal, context, non-goals, allowed changes, forbidden changes, verification, and done criteria.
- Handoff: Concise final report allowing another agent to continue without rereading the entire chat.
- Shared memory: Durable repo-owned project memory under `docs/memory/`.
