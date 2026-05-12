# Token Efficiency Rules

Use this guide to keep Codex, Claude Code, and human-driven agent runs focused.
The goal is to load the smallest context set that can safely complete the
mission.

## Default context order

For any task, load context in this order:

1. `AGENTS.md`
2. `CLAUDE.md` when running Claude Code
3. The GitHub Issue body, especially `Context Budget`, `Allowed Changes`,
   `Forbidden Changes`, relationships, and acceptance criteria
4. The single referenced implementation or design plan, only when the issue
   references one or the issue lacks enough context
5. One relevant `docs/context/<area>.md` file when implementation or review needs
   area context
6. Source files discovered with `rg`
7. Tests matching the touched code
8. `CHANGELOG.md` before assuming a feature is missing

Current release work is issue-based. Prefer the live GitHub Issue body over old
phase-table status when an issue exists.

Do not read broader docs unless the task requires them.

## Hard limits

- Read at most one implementation plan by default.
- Read at most one design document by default.
- Read at most one area context file by default.
- Do not read `spec.md` or `spec-v4.pdf` unless the user explicitly asks or the
  issue authorizes it.
- Do not scan the whole repository.
- Do not inspect frontend files for backend-only work unless API behavior is
  unclear.
- Do not inspect backend files for frontend-only work unless the UI depends on
  undocumented API behavior.
- Do not open large files before locating the relevant symbols, routes, tests, or
  components.
- For docs-only missions, do not read product source code unless the docs require
  exact service names, commands, paths, or API behavior.
- For review missions, read the PR diff first; open adjacent files only when the
  diff or tests need verification.
- Do not introduce SQLModel or refactor existing SQLAlchemy repositories while
  doing unrelated feature work. Load `docs/architecture/sqlmodel-bounded-models.md`
  only when a mission explicitly authorizes SQLModel evaluation or a bounded
  data-layer pilot.

## Search-first workflow

Start every implementation or review task with targeted discovery:

```bash
git status --short
rg "<symbol-or-route-or-component>"
rg --files <target-directory>
git diff --name-only main...HEAD
```

Prefer `rg` and `rg --files` over recursive dumps.

Avoid:

```bash
find . -type f
grep -R
cat <large-file>
```

## Context Budget for issues

Every implementation issue should include this section:

```md
## Context Budget

Read first:
- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `<single relevant plan or context doc>`

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

If no context budget is present, infer the smallest safe one from the issue,
phase plan, and mission queue. Do not broaden context just because more files
exist.

## Agent modes

### Planning mode

Use for Claude design, decomposition, architecture analysis, and issue migration.

Load:
- issue body
- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- relevant implementation/design plan when referenced
- one area context file when useful

Avoid source inspection unless required to validate feasibility or affected paths.

### Implementation mode

Use for Codex or Claude when changing code.

Load:
- issue body
- context budget
- relevant plan when referenced
- one area context file when useful
- exact source/test files found with `rg`

Do not read unrelated plans, designs, or source areas. Do not introduce a new data
abstraction such as SQLModel unless the issue explicitly authorizes it; preserve
existing SQLAlchemy Core repository patterns for ordinary backend work.

### Review mode

Load:
- PR description
- PR diff
- changed files
- referenced issue acceptance criteria
- adjacent code only when needed

Do not reread full phase plans unless the PR scope or acceptance criteria are
unclear.

## Shared-file caution

These files commonly conflict across parallel work and should be touched only
when the issue requires it:

- `CHANGELOG.md`
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- package lockfiles
- migrations
- frontend translation dictionaries
- release/operations docs

If multiple active issues need the same shared file, one PR should own the final
integration or later branches should rebase after the first PR merges.

## Required handoff fields

Every agent handoff must include context accounting:

```md
## Context Loaded
- ...

## Context Skipped
- ...

## Token Efficiency Notes
- Used `rg` before opening files: yes/no
- Read more than one plan: yes/no, reason
- Read broad source areas: yes/no, reason
```

The handoff should make unnecessary context expansion visible during review.

## Stop conditions

Stop and ask for human direction, or create a follow-up issue, when:

- the task requires reading multiple unrelated phase plans;
- the issue has no clear context budget and scope cannot be inferred;
- implementation requires changing files outside `Allowed Changes`;
- two active missions need the same shared files;
- `spec.md` or `spec-v4.pdf` appears necessary but was not explicitly authorized;
- a safety-sensitive task lacks a reviewed plan, especially destructive upgrade
  work or permission/ACL enforcement.
