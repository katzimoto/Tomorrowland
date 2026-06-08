# Context Budget Migration Plan

Use this document to migrate existing GitHub Issues and future missions to token-efficient execution.

## Migration goal

Every executable issue should tell agents exactly what to read, what to avoid, and where the safe edit boundaries are.

## Add this section to active issues

```md
## Context Budget

Read first:
- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `<single relevant implementation/design plan>`
- `<single relevant docs/context/*.md>`

Allowed source paths:
- ...

Allowed test paths:
- ...

Do not read unless explicitly needed:
- ...

Do not edit:
- `spec.md`
- `spec-v4.pdf`
- unrelated files outside the mission scope
```

## Claude prompt for issue migration

```txt
@claude migrate this issue to the Context Budget format.

Read:
1. AGENTS.md
2. docs/agents/token-efficiency.md
3. docs/agents/issue-context-template.md
4. the issue body
5. only the single phase/design plan already referenced by the issue

Do not implement code.
Do not inspect broad source areas unless needed to identify safe allowed paths.
Do not edit spec.md or spec-v4.pdf.

Update the issue body so it includes:
- Context Budget
- Allowed source paths
- Allowed test paths
- Do not read unless explicitly needed
- Do not edit
- Context-loaded handoff requirement in acceptance criteria

If the issue is too broad, propose child issues instead of expanding the context budget.
Stop after updating the issue or posting a proposed update comment.
```

## Batch migration order

1. Active `status:implementation` issues.
2. Active `status:planning` issues.
3. `status:parallel-safe` issues.
4. Blocked issues, after their blockers are clarified.
5. Deferred/conditional issues only when they become actionable.

## Review checklist

Before assigning an issue to an agent, verify:

- It references one implementation/design plan or explicitly says none is needed.
- It references at most one `docs/context/<area>.md` file.
- Allowed paths are narrower than the full repository.
- Forbidden paths include `spec.md` and `spec-v4.pdf` unless authorized.
- Acceptance criteria require context accounting in the handoff.
