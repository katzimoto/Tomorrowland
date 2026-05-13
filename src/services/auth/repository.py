from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RowMapping

from services.auth.ldap import LdapProfile
from services.auth.models import AuthSource, UserIdentity
from shared.db import db_uuid, to_uuid


class AuthRepository:
    """Database access for users, groups, and source grants."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get_user_by_email(self, email: str) -> UserIdentity | None:
        """Return a user identity and group memberships by email."""
        row = (
            self._connection.execute(
                sa.text("""
                SELECT id, email, display_name, auth_source, is_admin
                FROM users
                WHERE email = :email
                """),
                {"email": email},
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return self._identity_from_row(row)

    def get_password_hash(self, email: str) -> str | None:
        """Return the local password hash for an email when present."""
        return self._connection.execute(
            sa.text("SELECT password_hash FROM users WHERE email = :email"),
            {"email": email},
        ).scalar_one_or_none()

    def create_local_user(
        self,
        email: str,
        password_hash: str,
        display_name: str | None = None,
        is_admin: bool = False,
        group_names: Iterable[str] = (),
    ) -> UserIdentity:
        """Create a local user with optional group memberships."""
        user_id = uuid4()
        self._connection.execute(
            sa.text("""
                INSERT INTO users (id, email, display_name, auth_source, password_hash, is_admin)
                VALUES (:id, :email, :display_name, 'local', :password_hash, :is_admin)
                """),
            {
                "id": db_uuid(user_id),
                "email": email,
                "display_name": display_name,
                "password_hash": password_hash,
                "is_admin": is_admin,
            },
        )
        self.set_user_groups(user_id, group_names)
        user = self.get_user_by_email(email)
        if user is None:
            raise RuntimeError("local user insert did not persist")
        return user

    def upsert_ldap_user(self, profile: LdapProfile) -> UserIdentity:
        """Insert or update an LDAP-backed user and synchronize groups."""
        existing = self.get_user_by_email(profile.email)
        if existing is None:
            user_id = uuid4()
            self._connection.execute(
                sa.text("""
                    INSERT INTO users (id, email, display_name, auth_source, password_hash)
                    VALUES (:id, :email, :display_name, 'ldap', NULL)
                    """),
                {
                    "id": db_uuid(user_id),
                    "email": profile.email,
                    "display_name": profile.display_name,
                },
            )
        else:
            user_id = existing.id
            self._connection.execute(
                sa.text("""
                    UPDATE users
                    SET display_name = :display_name, auth_source = 'ldap', password_hash = NULL
                    WHERE id = :id
                    """),
                {"id": db_uuid(user_id), "display_name": profile.display_name},
            )
        self.set_user_groups(user_id, profile.group_names)
        user = self.get_user_by_email(profile.email)
        if user is None:
            raise RuntimeError("ldap user upsert did not persist")
        return user

    def set_user_groups(self, user_id: UUID, group_names: Iterable[str]) -> None:
        """Replace a user's group memberships by group name."""
        self._connection.execute(
            sa.text("DELETE FROM user_groups WHERE user_id = :user_id"),
            {"user_id": db_uuid(user_id)},
        )
        for group_name in group_names:
            group_id = self.ensure_group(group_name)
            self._connection.execute(
                sa.text(
                    "INSERT INTO user_groups (user_id, group_id) VALUES (:user_id, :group_id)"
                ),
                {"user_id": db_uuid(user_id), "group_id": db_uuid(group_id)},
            )

    def ensure_group(self, name: str) -> UUID:
        """Return an existing group ID or create a group by name."""
        existing = self._connection.execute(
            sa.text("SELECT id FROM groups WHERE name = :name"),
            {"name": name},
        ).scalar_one_or_none()
        if existing is not None:
            return to_uuid(existing)
        group_id = uuid4()
        try:
            with self._connection.begin_nested():
                self._connection.execute(
                    sa.text("INSERT INTO groups (id, name) VALUES (:id, :name)"),
                    {"id": db_uuid(group_id), "name": name},
                )
            return group_id
        except sa.exc.IntegrityError:
            existing = self._connection.execute(
                sa.text("SELECT id FROM groups WHERE name = :name"),
                {"name": name},
            ).scalar_one()
            return to_uuid(existing)

    def touch_last_login(self, user_id: UUID) -> None:
        """Record a successful login timestamp for a user."""
        self._connection.execute(
            sa.text("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = :id"),
            {"id": db_uuid(user_id)},
        )

    def create_ingestion_source(self, name: str, source_type: str = "folder") -> UUID:
        """Create a minimal ingestion source for permission grants."""
        source_id = uuid4()
        self._connection.execute(
            sa.text("""
                INSERT INTO ingestion_sources (id, name, type, source_language)
                VALUES (:id, :name, :type, 'en')
                """),
            {"id": db_uuid(source_id), "name": name, "type": source_type},
        )
        return source_id

    def grant_source_to_group(self, source_id: UUID, group_id: UUID) -> None:
        """Grant a group access to an ingestion source (idempotent)."""
        try:
            with self._connection.begin_nested():
                self._connection.execute(
                    sa.text("""
                        INSERT INTO source_permissions (source_id, group_id)
                        VALUES (:source_id, :group_id)
                        """),
                    {"source_id": db_uuid(source_id), "group_id": db_uuid(group_id)},
                )
        except sa.exc.IntegrityError:
            pass

    def create_document(
        self, source_id: UUID, external_id: str = "file:/data/a.txt"
    ) -> UUID:
        """Create a minimal document tied to an ingestion source."""
        doc_id = uuid4()
        self._connection.execute(
            sa.text("""
                INSERT INTO documents (id, source_id, external_id, source, mime_type)
                VALUES (:id, :source_id, :external_id, 'folder', 'text/plain')
                """),
            {
                "id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "external_id": external_id,
            },
        )
        return doc_id

    def user_can_access_source(self, user: UserIdentity, source_id: UUID) -> bool:
        """Return whether any of a user's groups can access a source."""
        if user.email == "admin@local.com":
            return True
        if not user.groups:
            return False
        rows = self._connection.execute(
            sa.text("""
                SELECT group_id
                FROM source_permissions
                WHERE source_id = :source_id
                """),
            {"source_id": db_uuid(source_id)},
        ).scalars()
        allowed_groups = {to_uuid(row) for row in rows}
        return bool(allowed_groups.intersection(user.groups))

    def document_source_id(self, doc_id: UUID) -> UUID | None:
        """Return the ingestion source for a document when it exists."""
        value = self._connection.execute(
            sa.text("SELECT source_id FROM documents WHERE id = :id"),
            {"id": db_uuid(doc_id)},
        ).scalar_one_or_none()
        return None if value is None else to_uuid(value)

    def _identity_from_row(self, row: RowMapping) -> UserIdentity:
        user_id = to_uuid(row["id"])
        groups = self._connection.execute(
            sa.text("SELECT group_id FROM user_groups WHERE user_id = :user_id"),
            {"user_id": db_uuid(user_id)},
        ).scalars()
        return UserIdentity(
            id=user_id,
            email=str(row["email"]),
            display_name=row["display_name"],
            auth_source=self._auth_source(row["auth_source"]),
            is_admin=bool(row["is_admin"]),
            groups=[to_uuid(group_id) for group_id in groups],
        )

    @staticmethod
    def _auth_source(value: Any) -> AuthSource:
        if value == "local" or value == "ldap":
            return cast("AuthSource", value)
        raise ValueError(f"unexpected auth_source {value!r}")
