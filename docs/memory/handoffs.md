# Tomorrowland Handoffs

Shared record for concise cross-agent handoffs that remain useful after a chat or tool session ends.

## Handoff template

```md
## YYYY-MM-DD — Short title

Status: Active | Done | Watch
Source: issue | PR | commit | chat summary

What changed:
- ...

Verification:
- ...

Open risks:
- ...

Next agent prompt:
- ...
```

## 2026-05-20 — Agent skills and memory branch

Status: Active
Source: project manager chat summary

What changed:
- Started branch `chore/add-agent-skill-pack`.
- Added shared Claude/OpenCode skills under `.claude/skills/`.
- Added shared memory policy and seed memory files.

Verification:
- File creation verified through GitHub connector commit responses.

Open risks:
- OpenCode agent definitions still need final creation and review.
- No local runtime validation was run.

Next agent prompt:
- Review branch `chore/add-agent-skill-pack` for skill discoverability, OpenCode agent syntax, and memory policy clarity.
