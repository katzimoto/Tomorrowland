# Agent Documentation Index

This directory contains focused agent guidance. Root `AGENTS.md` remains the primary instruction file, but agents should load only the detailed file relevant to the current task.

## Files

| File | Use when |
|---|---|
| `token-efficiency.md` | Any agent task. Defines context order, hard limits, and required context accounting. |
| `issue-context-template.md` | Creating or refining GitHub Issues for Codex/Claude execution. |

## Default use

For most work:

1. Read `AGENTS.md`.
2. Read the GitHub Issue body.
3. Read `docs/agents/token-efficiency.md`.
4. Read only the single implementation/design/context file referenced by the issue.

Do not load every file in this directory by default.
