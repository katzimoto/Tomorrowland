# CLAUDE.md — Tomorrowland Claude Code Entry Point

Claude Code must treat `AGENTS.md` as the primary repository instruction file.

Before taking any action, Claude must read:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. The GitHub Issue body, especially `Context Budget`, `Allowed Changes`,
   `Forbidden Changes`, relationships, and acceptance criteria
4. The single relevant implementation/design plan only when the issue references
   one or when the issue lacks enough context
5. One relevant `docs/context/<area>.md` file when implementation or review needs
   area context
6. `CHANGELOG.md` before assuming a feature is missing

Current executable release work is issue-based. Prefer the release queue in
`AGENTS.md` and the live GitHub Issue body over stale phase-table status.

Do not duplicate project rules here. `AGENTS.md` is the source of truth for:

- current release queue
- multi-agent orchestration
- GitHub Issue workflow
- issue relationships and blockers
- parallel-safe agent execution
- branch and PR coordination
- review routing
- handoff format
- backend/frontend conventions
- safety and documentation rules

Use `docs/agents/token-efficiency.md` for context limits, search-first behavior,
and required `Context Loaded` / `Context Skipped` / `Token Efficiency Notes`
handoff fields.

Claude is preferred for planning, architecture/security review, broad UI
localization, UX/text consistency, docs polish, issue decomposition, and reviewer
reports. Implementation is allowed when the issue or user explicitly requests it
and the scope is bounded.

For planning-only tasks, stop after posting the requested plan or review. Do not
implement product code during a planning-only task.
