from __future__ import annotations

from uuid import UUID

from sqlalchemy import MetaData


def db_uuid(value: UUID | str) -> str:
    """Convert a UUID or UUID hex string to its hex string for database storage."""
    return value.hex if isinstance(value, UUID) else value.replace("-", "")


def to_uuid(value: object) -> UUID:
    """Convert a database value back to a UUID."""
    return value if isinstance(value, UUID) else UUID(str(value))


metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)
