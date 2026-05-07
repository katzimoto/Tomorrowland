# Phase 02: Auth And Permissions

## Goal

Implement authentication and backend permission enforcement.

## Scope

- Local auth.
- LDAP auth boundary/interface.
- Unified user table usage.
- JWT creation and validation.
- User/group membership.
- Source permission enforcement.
- Admin-only guards.

## Validation

- Unit tests cover password auth, LDAP fallback behavior, JWT payloads, group
  permission checks, and admin checks.
- API tests cover login, logout, current user, unauthorized, and forbidden paths.

## Acceptance Criteria

- All protected APIs have a consistent user context contract.
- Admin-only operations cannot be reached by non-admin users.
- Permissions are enforced in backend code, not only UI.
