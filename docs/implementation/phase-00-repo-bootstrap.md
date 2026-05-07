# Phase 00: Repo Bootstrap And Planning Docs

## Goal

Make the repository reviewable and CI-ready without adding application code.

## Scope

- Split the v4 spec into logical-spec and phase-plan documentation.
- Add a spec gap review document.
- Add repository hygiene files.
- Add GitHub issue and PR templates.
- Add GitHub Actions workflows that are useful before app code exists.

## Out Of Scope

- Service code.
- Docker Compose runtime implementation.
- Database migrations.
- Application tests.

## Implementation Steps

- Create `docs/logical-spec.md`.
- Create `docs/review/spec-gaps.md`.
- Create `docs/implementation/README.md`.
- Create one phase plan file for phases 00 through 08.
- Add `.gitignore`, `.editorconfig`, `.env.example`, and `CHANGELOG.md`.
- Add PR and issue templates under `.github/`.
- Add CI, Codex Developer, Codex Reviewer, and security workflows.

## Validation

- Confirm all expected files are present.
- Run YAML syntax checks available locally.
- Run `git status --short`.
- Stop for Reviewer agent review.

## Acceptance Criteria

- `spec.md` and `spec-v4.pdf` are unchanged.
- GitHub Actions exist and are path-aware or manifest-aware.
- Phase plans are complete enough for separate PR review.
