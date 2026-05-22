# CLAUDE.md — Tomorrowland Claude Code Entry Point

Claude Code must treat `AGENTS.md` as the primary repository instruction file.

Before taking any action, Claude must read:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. The GitHub Issue body, especially `Context Budget`, `Allowed Changes`,
   `Forbidden Changes`, relationships, and acceptance criteria
5. The single relevant implementation/design plan only when the issue references
   one or when the issue lacks enough context
6. One relevant `docs/context/<area>.md` file when implementation or review needs
   area context
7. `CHANGELOG.md` before assuming a feature is missing

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

Use `docs/agents/coding-behavior.md` for the execution discipline on every
non-trivial task: think before coding, keep changes simple, make surgical edits,
turn the request into verifiable goals, and report verification honestly.

Claude is preferred for planning, architecture/security review, broad UI
localization, UX/text consistency, docs polish, issue decomposition, and reviewer
reports. Implementation is allowed when the issue or user explicitly requests it
and the scope is bounded.

Before implementation, Claude should restate the goal, state assumptions,
identify the smallest safe change, and name the verification step. Before final
handoff, Claude should summarize changed files, verification performed, skipped
checks, and remaining risks.

For planning-only tasks, stop after posting the requested plan or review. Do not
implement product code during a planning-only task.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
