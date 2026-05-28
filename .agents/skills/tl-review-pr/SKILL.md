# Skill: Review a Tomorrowland PR

Invoke this when asked to review another agent's pull request.

## Steps

1. Read the PR description and referenced issue body.
2. Read the PR diff. Prefer `git diff` or GitHub diff view over opening every
   changed file.
3. Verify the changes match the issue acceptance criteria.
4. Run targeted checks for the touched area:
   ```bash
   uv run ruff check src/ tests/ migrations/
   uv run mypy src --strict
   uv run pytest tests/unit/test_<area>.py -q
   ```
5. Check for common mistakes:
   - Hardcoded secrets or default credentials
   - Missing permission guards on new endpoints
   - Missing downgrade in new migrations
   - Bypassed feature flags
   - Unsafe document path handling
   - SQL string interpolation
6. Verify tests cover the new behavior, not just the happy path.
7. Post a concise review with blockers, warnings, suggestions, and a verdict.

## Review prompts

```
@claude review this PR against AGENTS.md, the issue, architecture consistency, and edge cases.
@codex review this PR for correctness, tests, typing, lint, regressions, and CI failures.
```

## Stop conditions

- Stop if the PR mixes unrelated concerns (release blocker + feature + polish).
- Stop if the PR changes shared files that another active PR also touches.
- Stop if security-sensitive changes lack tests or were not planned/reviewed by
  Claude.
