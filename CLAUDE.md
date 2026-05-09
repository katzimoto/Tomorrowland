# CLAUDE.md — Neverland Claude Code Entry Point

Claude Code must treat `AGENTS.md` as the primary repository instruction file.

Before taking any action, Claude must read:

1. `AGENTS.md`
2. The single relevant phase plan in `docs/implementation/`
3. `docs/implementation/README.md` only when mission/phase indexing is needed
4. `CHANGELOG.md` before assuming a feature is missing

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

For issue-based migration work, Claude must follow the controller issue instructions and stop after posting the required migration report. Do not implement product code during a migration-only task.
