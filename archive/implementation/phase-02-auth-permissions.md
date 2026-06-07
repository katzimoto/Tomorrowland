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

## Implementation Notes

- Local auth uses bcrypt password hashes stored in `users.password_hash`.
- LDAP support is represented by an adapter boundary that returns normalized
  profile/group data; real LDAP network binding is deferred behind that boundary.
- JWTs carry the Phase 02 user context: user ID, email, admin flag, auth source,
  group IDs, and expiry.
- Document access is enforced through source-level grants resolved from
  `source_permissions`, matching the Phase 01 access decision.

## Validation

- Unit tests cover password auth, LDAP fallback behavior, JWT payloads, group
  permission checks, and admin checks.
- API tests cover login, logout, current user, unauthorized, and forbidden paths.

## Acceptance Criteria

- All protected APIs have a consistent user context contract.
- Admin-only operations cannot be reached by non-admin users.
- Permissions are enforced in backend code, not only UI.
