# Documenting Features

Quick-reference mapping: what to update in the MkDocs wiki when you make a change.

## Wiki Structure

| Section | Audience | What goes here |
|---|---|---|
| [Home](../index.md) | Everyone | Only update the "I want to…" links if a new major doc is added |
| [Getting Started](../development/local-dev.md) | Newcomers | Setup steps, architecture overview, logical spec |
| [Deploy & Operate](../operations/production-compose.md) | Operators | Deployment guides, air-gapped workflow, pipeline, model config |
| [Develop](../context/README.md) | Developers | Context maps for backend, search, extraction, frontend, ACL |
| [Design & Specs](../design/README.md) | Architects | Feature specs, design decisions, permissions model, logging, metrics |
| [Agent Guide](README.md) | AI agents | Coding behavior, token efficiency, templates (this file's section) |
| [API Reference](../api/search.md) | Developers | Auto-generated from docstrings via mkdocstrings |
| [Reference](../memory/glossary.md) | Everyone | Glossary, architecture decisions |
| [History & Roadmap](../roadmap.md) | Everyone | Links to GitHub Issues, CHANGELOG, git log |

## Change → Docs Mapping

### New config/env var

- Add to `.env.example` and `.env.airgap.example`
- Update the relevant operations doc (e.g., `docs/operations/production-compose.md`, `docs/operations/air-gapped-deployment.md`)
- If it's an AI/LLM setting, update `docs/operators/ai-surfaces.md`

### New API endpoint or route

- Update the relevant context map in `docs/context/` (backend-api.md, search.md, etc.)
- Add a `::: module.path` entry to the relevant `docs/api/*.md` stub file
- If it's an admin endpoint, update `docs/operations/production-compose.md` or the relevant operations doc

### New service, worker, or runtime component

- Add to `docs/architecture/overview.md` in the Runtime Components list
- Update `docs/operations/pipeline-workers.md` if it's a pipeline stage
- Update `docs/operations/production-compose.md` if it needs a Compose service definition

### Schema change (new table, column, migration)

- Update `docs/architecture/overview.md` if it changes the core data model
- Update `docs/design/sources-permissions-model.md` if it affects the permissions model
- The migration itself is self-documenting (upgrade + downgrade)

### New UI page or component

- If it has a design spec, add it to `docs/design/` and the Design & Specs nav
- Update `docs/design/user-ui-spec.md` for shared patterns

### New or changed feature flag

- Update `docs/operators/ai-surfaces.md` for AI-related flags
- Update the relevant operations doc for infra flags
- Add to `.env.example` and `.env.airgap.example`

### Security, auth, or permission change

- Update `docs/context/acl-audit.md`
- Update `docs/design/sources-permissions-model.md` if it changes the access model
- Update `docs/architecture/overview.md` if it adds a new auth provider

### Search, RAG, or indexing change

- Update `docs/context/search.md`
- Update `docs/operators/ai-surfaces.md` for RAG configuration changes
- Update `docs/api/search.md` or `docs/api/rag.md` stub file if public APIs change

### CI, build, or release process change

- Update `docs/operations/release-notes-rc.md` for release-impacting changes
- Update `docs/operations/air-gapped-deployment.md` for air-gapped build changes
- Update `CHANGELOG.md`

### Bug fix that changes expected behavior

- Update the doc that describes the now-corrected behavior
- If the bug was user-visible, update `CHANGELOG.md`

## Docstring-Driven API Reference

The `docs/api/` pages are auto-generated from Python docstrings using mkdocstrings. To keep them accurate:

- Write Google-style docstrings for all public classes, methods, and functions
- Include type annotations in signatures (already enforced by mypy)
- Update the `::: module.path` entries in `docs/api/*.md` when adding new public modules
- CI verifies these generate correctly via `mkdocs build --strict`

## Verification

Before marking a PR ready, run:

```bash
uv run mkdocs build --strict
```

CI runs this automatically for PRs that touch `docs/**`, `**/*.md`, `mkdocs.yml`, `pyproject.toml`, or `uv.lock`.
