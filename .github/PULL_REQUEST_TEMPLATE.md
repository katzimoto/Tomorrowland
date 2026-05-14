## Mission

Closes #<issue-number>.

## Changes

- 

## Changed Files Audit

Run `git diff --name-only <target-branch>...HEAD` and paste the output below.

```
# paste output here
```

- [ ] Changed files listed above
- [ ] Every changed file is required by this issue
- [ ] No local agent artifacts (`.opencode_auth.json`, `token_opencode.txt`, root `main`)
- [ ] No unrelated `.gitignore` additions (use `.git/info/exclude` for local tooling)
- [ ] No formatting-only or execute-bit-only diffs outside scope
- [ ] `bash scripts/check-pr-cleanliness.sh <target-branch>` passed (or N/A; reason: )

## Tests / Checks

- [ ] `ruff check src/ tests/ migrations/`
- [ ] `mypy src --strict`
- [ ] `pytest tests/unit/test_<area>.py -q`
- [ ] `pytest tests/integration/test_<area>.py -q`
- [ ] `npm --prefix frontend run lint`
- [ ] `npm --prefix frontend run typecheck`
- [ ] `npm --prefix frontend run test`
- [ ] `npm --prefix frontend run build`
- [ ] Not run; reason: 

## Risks

- 

## Notes for Reviewers

- 

## Agent Handoff

### Completed

- 

### Remaining

- 

### Tests Executed

- 

### Context Loaded

- 

### Context Skipped

- 

### Token Efficiency Notes

- Used `rg` before opening files: yes/no
- Read more than one plan: yes/no, reason
- Read broad source areas: yes/no, reason

### Risks

- 

### Suggested Next Steps

- 
