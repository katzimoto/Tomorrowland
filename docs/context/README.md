# Context Maps

Context maps are compact area summaries for agent work. They are intentionally smaller than implementation plans and source files.

Use them to answer:

- Which files matter for this area?
- Which tests usually apply?
- Which patterns should agents preserve?
- Which files should agents avoid unless explicitly needed?

## Available maps

| File | Area |
|---|---|
| `backend-api.md` | FastAPI routes, auth guards, persistence boundaries. |
| `frontend.md` | React/Vite UI work and frontend testing. |
| `search.md` | Elasticsearch/Qdrant/hybrid search work. |
| `extraction.md` | Document extraction registry and file-type handlers. |

Agents should read at most one context map by default.
