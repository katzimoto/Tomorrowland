# CLAUDE.md — Neverland Claude Code Entry Point

Claude Code must treat `AGENTS.md` as the primary repository instruction file.

Before taking any action, Claude must read:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. The GitHub Issue body, especially any `Context Budget`
4. The single relevant phase/design plan in `docs/implementation/` or `docs/design/`
5. One relevant `docs/context/<area>.md` file when implementation or review needs area context
6. `docs/implementation/README.md` only when mission/phase indexing is needed
7. `CHANGELOG.md` before assuming a feature is missing

Do not duplicate project rules here. `AGENTS.md` is the source of truth for:

- mission queue
- multi-agent orchestration
- GitHub Issue workflow
- issue relationships and blockers
- parallel-safe agent execution
- branch and PR coordination
- review routing
- handoff format
- backend/frontend conventions
- safety and documentation rules

Use `docs/agents/token-efficiency.md` for context limits, search-first behavior, and required `Context Loaded` / `Context Skipped` / `Token Efficiency Notes` handoff fields.

For issue-based migration work, Claude must follow the controller issue instructions and stop after posting the required migration report. Do not implement product code during a migration-only task.
