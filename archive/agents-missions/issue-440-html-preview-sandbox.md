# Claude Mission: Issue #440 — Sandbox HTML Preview

## Mission

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

Implement GitHub issue #440:

**Security: Sandbox HTML preview iframe (replace dangerouslySetInnerHTML)**

This is the first MVP step for the high-fidelity document viewer track.

- Parent issue: #453
- Direct issue: #440
- Target branch: `main`
- Expected PR target: `main`

This is an isolated security fix. Keep the implementation surgical.

---

## Skills and Plugins You Should Use

Use the Tomorrowland project skills/plugins where they help. Prefer the narrowest useful tool for each step.

### Required / recommended Claude skills

Use these skills if available in the runtime:

1. `.claude/skills/tomorrowland-project-context/SKILL.md`
   - Load current Tomorrowland project conventions and terminology.

2. `.claude/skills/safe-implementation/SKILL.md`
   - Keep the diff small, scoped, testable, and reversible.

3. `.claude/skills/frontend-uiux-guardian/SKILL.md`
   - Preserve current UI layout and behavior while changing the rendering boundary.

4. `.claude/skills/bug-debugging-playbook/SKILL.md`
   - Use only if tests fail or the component behavior is unclear.

5. `.claude/skills/agent-handoff/SKILL.md`
   - Use at the end to report changed files, tests, risks, and next steps.

6. `.claude/skills/shared-memory/SKILL.md`
   - Use only if you need to update durable project memory after implementation. Do not update memory for routine code changes unless there is a durable decision or handoff worth preserving.

Do **not** load broad or unrelated skills. Do **not** spend tokens exploring unrelated project areas.

### Plugins / external tools

You may use:

- GitHub plugin/MCP to read issue #440, parent #453, and open the PR.
- Local shell tools such as `rg`, `sed`, `git diff`, `npm`, and the project test runner.
- Code search for the exact files listed below.

Do **not** use:

- Jira or Confluence plugins for this task.
- Broad web research.
- Cloud conversion services.
- Any backend service or database tools.

---

## Required Reading

Read these first, in this order:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. `docs/design/document-viewer-implementation-guardrails.md`
5. GitHub issue #440
6. GitHub issue #453 only enough to understand parent scope
7. `frontend/src/features/documents/renderers/HtmlPreview.tsx`
8. `frontend/src/features/documents/renderers/HtmlPreview.test.tsx`
9. `frontend/src/features/documents/renderers/renderers.module.css`

Do **not** read:

- `spec.md`
- `spec-v4.pdf`
- unrelated backend files
- unrelated renderer files unless a local import/test requires it

Use `rg` before opening additional files.

---

## Goal

Replace the current HTML preview implementation with a sandboxed iframe so untrusted HTML is no longer injected into the Tomorrowland app DOM.

The user-facing behavior should remain the same as much as possible: HTML documents should still render in the document viewer area, but scripts must not run in the app origin.

---

## Implementation Requirements

### Replace unsafe rendering

In `HtmlPreview.tsx`:

- Remove all `dangerouslySetInnerHTML` usage.
- Remove the local `DOMParser` sanitizer if it is only used by this component.
- Render with a sandboxed iframe using `srcDoc`.

Expected shape:

```tsx
<iframe
  srcDoc={html}
  sandbox="allow-same-origin"
  title="HTML document preview"
/>
```

### Security requirements

The iframe must:

- Use `srcDoc` to receive the HTML content.
- Include `sandbox="allow-same-origin"`.
- **Not** include `allow-scripts`.
- Have a descriptive `title` attribute.

Do not add script execution permissions.

### UI/layout requirements

Preserve the existing document viewer layout:

- The preview should fill the available renderer area.
- No unnecessary visual regression.
- Use the existing renderer CSS module where appropriate.
- Avoid inline styles if a CSS class already fits the project style.

### Scope limits

Allowed source paths:

- `frontend/src/features/documents/renderers/HtmlPreview.tsx`
- `frontend/src/features/documents/renderers/HtmlPreview.test.tsx`
- `frontend/src/features/documents/renderers/renderers.module.css`

Do not edit:

- backend code
- other renderer components
- `PreviewPane.tsx` unless strictly necessary
- `spec.md`
- `spec-v4.pdf`
- broad app shell files

---

## Test Requirements

Update or add tests for `HtmlPreview`.

Required assertions:

- `HtmlPreview` renders an `<iframe>`.
- The iframe has `srcDoc` equal to the provided HTML string.
- The iframe has `sandbox="allow-same-origin"`.
- The sandbox value does not contain `allow-scripts`.
- The iframe has a descriptive accessible title.
- The old `dangerouslySetInnerHTML` path is gone from the component source.

Run the narrowest relevant frontend test command for this component. If the exact command is not obvious, inspect `frontend/package.json` and use the project’s existing Vitest pattern.

Also run a lightweight static check if the project provides one and it is cheap for the frontend scope.

Do not run the full backend suite for this task.

---

## Best Practices

- Create a small branch for the work, for example: `fix/html-preview-sandbox`.
- Keep the diff minimal.
- Preserve public component props unless a change is required.
- Prefer explicit test assertions over snapshots.
- Do not broaden the task into the rest of the document viewer project.
- Do not introduce new dependencies.
- Do not implement the larger document viewer feature in this PR.
- If a test is impossible or flaky, explain exactly why and what you verified instead.

---

## Acceptance Checklist

Before opening the PR, confirm:

- [ ] `dangerouslySetInnerHTML` is no longer used in `HtmlPreview.tsx`.
- [ ] HTML content is rendered through iframe `srcDoc`.
- [ ] iframe sandbox is exactly `allow-same-origin` or equivalent without `allow-scripts`.
- [ ] iframe has an accessible title.
- [ ] Existing HTML preview layout remains usable.
- [ ] Relevant frontend tests pass.
- [ ] No unrelated files were changed.

---

## Pull Request Requirements

Open a PR targeting `main`.

PR title suggestion:

```text
fix: sandbox HTML document preview
```

PR body must include:

```markdown
## Summary

- Replaced unsafe HTML preview DOM injection with a sandboxed iframe.
- Removed `dangerouslySetInnerHTML` from `HtmlPreview`.
- Added/updated tests for iframe sandbox behavior.

## Security behavior

HTML preview content is now rendered through an iframe `srcDoc` with `sandbox="allow-same-origin"` and no `allow-scripts`, preventing preview scripts from executing in the app origin.

## Tests

- <exact commands run>

Fixes #440
Part of #453
```

---

## Final Response Format

When done, report:

1. Branch name.
2. PR link.
3. Files changed.
4. Exact tests run and result.
5. Security behavior after the change.
6. Any follow-up needed.

If you cannot complete the implementation, stop and report the exact blocker with the smallest useful next step.
