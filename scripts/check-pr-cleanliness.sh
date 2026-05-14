#!/usr/bin/env bash
# check-pr-cleanliness.sh — flag high-risk local artifacts and out-of-scope changes.
#
# Usage:
#   bash scripts/check-pr-cleanliness.sh [target-branch]
#
# target-branch defaults to main.  For feature-branch sub-PRs pass the feature
# branch name, e.g.:
#   bash scripts/check-pr-cleanliness.sh feature/pipeline-jobs
#
# Exit codes:
#   0  — no issues found
#   1  — one or more issues found (blocks CI or informs the author)

set -euo pipefail

TARGET="${1:-main}"
FAILED=0

changed_files() {
    if git merge-base "${TARGET}" HEAD &>/dev/null; then
        git diff --name-only "${TARGET}...HEAD"
    else
        # No merge base (e.g. orphan branch in CI) — fall back to two-dot diff
        git diff --name-only "${TARGET}" HEAD 2>/dev/null || true
    fi
}

warn() {
    echo "WARN: $*" >&2
    FAILED=1
}

echo "=== PR cleanliness check (base: ${TARGET}) ==="
echo

# ── 1. List changed files ────────────────────────────────────────────────────
echo "Changed files vs ${TARGET}:"
FILES=$(changed_files)
if [ -z "$FILES" ]; then
    echo "  (none)"
else
    echo "$FILES" | sed 's/^/  /'
fi
echo

# ── 2. High-risk local artifact files ────────────────────────────────────────
ARTIFACTS=(
    ".opencode_auth.json"
    "token_opencode.txt"
)

for artifact in "${ARTIFACTS[@]}"; do
    if echo "$FILES" | grep -qxF "$artifact"; then
        warn "Local agent artifact in diff: ${artifact}"
        warn "  Add it to .git/info/exclude or your global gitignore instead."
    fi
done

# Root-level file named exactly 'main' (no extension) — common agent scaffold artifact
if echo "$FILES" | grep -qxE "main"; then
    warn "Root-level file named 'main' in diff — likely an accidental agent artifact."
fi

# ── 3. Untracked local artifacts that should never be committed ───────────────
for artifact in "${ARTIFACTS[@]}" "main"; do
    if [ -f "${artifact}" ] && ! git ls-files --error-unmatch "${artifact}" &>/dev/null; then
        warn "Untracked local artifact present on disk: ${artifact}"
        warn "  Run: echo '${artifact}' >> .git/info/exclude"
    fi
done

# ── 4. .gitignore changes ─────────────────────────────────────────────────────
if echo "$FILES" | grep -qxF ".gitignore"; then
    echo "NOTE: .gitignore is modified in this PR."
    echo "      Verify every added line is intentional team-wide policy,"
    echo "      not a local tooling exclusion (those belong in .git/info/exclude)."
    echo
fi

# ── 5. Execute-bit-only diffs ─────────────────────────────────────────────────
CHMOD_ONLY=$(git diff "${TARGET}...HEAD" --diff-filter=M --summary 2>/dev/null \
    | grep "^ mode change" || true)
if [ -n "$CHMOD_ONLY" ]; then
    warn "Execute-bit-only changes detected:"
    echo "$CHMOD_ONLY" | sed 's/^/  /' >&2
    warn "  Stage only if this chmod is intentional and in scope."
fi

# ── Result ────────────────────────────────────────────────────────────────────
echo
if [ "$FAILED" -eq 0 ]; then
    echo "OK: no cleanliness issues found."
else
    echo "FAIL: review the warnings above before opening the PR."
    exit 1
fi
