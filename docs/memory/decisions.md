# Tomorrowland Decisions

Shared record for durable architecture, product, and agent workflow decisions.

## 2026-05-20 — Repo memory is the durable record

Status: Active
Source: project manager chat summary

Decision:
- Store durable project memory in `docs/memory/*.md`.
- Use optional indexing only as a retrieval helper.
- Keep important decisions visible in normal code review.

Impact:
- Claude, OpenCode, and Codex should read relevant memory before substantial work.
- New durable decisions should be added here in compact form.

Next action:
- Keep this file short and update stale entries when decisions change.
