from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _audit_log, _fmt_dt
from services.api.main import current_user
from services.api.schemas import (
    AddChildGroupRequest,
    AddUserToGroupRequest,
    AdminUpdateUserGroupsRequest,
    CreateGroupRequest,
    CreateUserRequest,
)
from services.auth.models import TokenPayload
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.permissions.enforcer import require_admin
from shared.db import db_uuid, to_uuid

router = APIRouter(tags=["admin"])


@router.get("/admin/users")
def admin_list_users(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(
            sa.text("""
                SELECT id, email, display_name, auth_source, is_admin, created_at
                FROM users ORDER BY created_at DESC
                """)
        ).mappings()
        return [
            {
                "id": str(to_uuid(row["id"])),
                "email": row["email"],
                "display_name": row["display_name"],
                "auth_source": row["auth_source"],
                "is_admin": row["is_admin"],
                "created_at": _fmt_dt(row["created_at"]),
            }
            for row in rows
        ]


@router.post("/admin/users", status_code=201)
def admin_create_user(
    body: CreateUserRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        identity = auth_repo.create_local_user(
            email=body.email,
            password_hash=hash_password(body.password),
            display_name=body.display_name,
            is_admin=body.is_admin,
            group_names=body.group_names,
        )
        _audit_log(
            connection,
            user.sub,
            "create",
            "user",
            str(identity.id),
            {"email": identity.email},
        )
        return {
            "id": str(identity.id),
            "email": identity.email,
            "display_name": identity.display_name,
            "is_admin": identity.is_admin,
        }


@router.delete("/admin/users/{user_id}", status_code=204)
def admin_delete_user(
    user_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    require_admin(user)
    if user_id == user.sub:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    with request.app.state.engine.begin() as connection:
        result = connection.execute(
            sa.text("DELETE FROM users WHERE id = :id"),
            {"id": user_id.hex},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        _audit_log(connection, user.sub, "delete", "user", str(user_id))


@router.get("/admin/users/{user_id}")
def admin_get_user(
    user_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        row = (
            connection.execute(
                sa.text("""
                SELECT id, email, display_name, auth_source, is_admin, created_at
                FROM users WHERE id = :id
                """),
                {"id": user_id.hex},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="User not found")
        groups = (
            connection.execute(
                sa.text("""
                SELECT g.id, g.name
                FROM user_groups ug
                JOIN groups g ON g.id = ug.group_id
                WHERE ug.user_id = :user_id
                ORDER BY g.name
                """),
                {"user_id": user_id.hex},
            )
            .mappings()
            .all()
        )
        return {
            "id": str(to_uuid(row["id"])),
            "email": row["email"],
            "display_name": row["display_name"],
            "auth_source": row["auth_source"],
            "is_admin": row["is_admin"],
            "created_at": _fmt_dt(row["created_at"]),
            "groups": [{"id": str(to_uuid(g["id"])), "name": g["name"]} for g in groups],
        }


@router.put("/admin/users/{user_id}/groups")
def admin_set_user_groups(
    user_id: UUID,
    body: AdminUpdateUserGroupsRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, list[dict[str, str]]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.set_user_groups(user_id, body.group_names)
        groups = (
            connection.execute(
                sa.text("""
                SELECT g.id, g.name
                FROM user_groups ug
                JOIN groups g ON g.id = ug.group_id
                WHERE ug.user_id = :user_id
                ORDER BY g.name
                """),
                {"user_id": user_id.hex},
            )
            .mappings()
            .all()
        )
        _audit_log(
            connection,
            user.sub,
            "update",
            "user",
            str(user_id),
            {"groups": list(body.group_names)},
        )
        return {
            "groups": [{"id": str(to_uuid(g["id"])), "name": g["name"]} for g in groups],
        }


@router.get("/admin/groups")
def admin_list_groups(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        rows = connection.execute(sa.text("SELECT id, name FROM groups ORDER BY name")).mappings()
        return [{"id": str(to_uuid(row["id"])), "name": row["name"]} for row in rows]


@router.post("/admin/groups", status_code=201)
def admin_create_group(
    body: CreateGroupRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(body.name)
        _audit_log(connection, user.sub, "create", "group", str(group_id))
        return {"id": str(group_id), "name": body.name}


@router.get("/admin/groups/{group_id}/users")
def admin_list_group_users(
    group_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        group_row = connection.execute(
            sa.text("SELECT id FROM groups WHERE id = :id"),
            {"id": db_uuid(group_id)},
        ).first()
        if group_row is None:
            raise HTTPException(status_code=404, detail="Group not found")
        rows = (
            connection.execute(
                sa.text("""
                    SELECT u.id, u.email, u.display_name
                    FROM user_groups ug
                    JOIN users u ON u.id = ug.user_id
                    WHERE ug.group_id = :group_id
                    ORDER BY u.email
                """),
                {"group_id": db_uuid(group_id)},
            )
            .mappings()
            .all()
        )
        return [
            {
                "id": str(to_uuid(r["id"])),
                "email": r["email"],
                "display_name": r["display_name"],
            }
            for r in rows
        ]


@router.post("/admin/groups/{group_id}/users", status_code=201)
def admin_add_user_to_group(
    group_id: UUID,
    body: AddUserToGroupRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, str]:
    require_admin(user)
    user_id = UUID(body.user_id)
    with request.app.state.engine.begin() as connection:
        group_row = connection.execute(
            sa.text("SELECT id FROM groups WHERE id = :id"),
            {"id": db_uuid(group_id)},
        ).first()
        if group_row is None:
            raise HTTPException(status_code=404, detail="Group not found")
        try:
            with connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO user_groups (user_id, group_id) VALUES (:user_id, :group_id)"
                    ),
                    {"user_id": db_uuid(user_id), "group_id": db_uuid(group_id)},
                )
        except sa.exc.IntegrityError:
            pass
        _audit_log(
            connection,
            user.sub,
            "add_user_to_group",
            "group",
            str(group_id),
            {"user_id": str(user_id)},
        )
        return {"group_id": str(group_id), "user_id": str(user_id)}


@router.delete("/admin/groups/{group_id}/users/{user_id}", status_code=204)
def admin_remove_user_from_group(
    group_id: UUID,
    user_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        group_row = connection.execute(
            sa.text("SELECT id FROM groups WHERE id = :id"),
            {"id": db_uuid(group_id)},
        ).first()
        if group_row is None:
            raise HTTPException(status_code=404, detail="Group not found")
        connection.execute(
            sa.text("DELETE FROM user_groups WHERE user_id = :user_id AND group_id = :group_id"),
            {"user_id": db_uuid(user_id), "group_id": db_uuid(group_id)},
        )
        _audit_log(
            connection,
            user.sub,
            "remove_user_from_group",
            "group",
            str(group_id),
            {"user_id": str(user_id)},
        )


@router.get("/admin/groups/{group_id}/children")
def admin_list_group_children(
    group_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, str]]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        group_row = connection.execute(
            sa.text("SELECT id FROM groups WHERE id = :id"),
            {"id": db_uuid(group_id)},
        ).first()
        if group_row is None:
            raise HTTPException(status_code=404, detail="Group not found")
        rows = (
            connection.execute(
                sa.text("""
                    SELECT g.id, g.name
                    FROM group_memberships gm
                    JOIN groups g ON g.id = gm.child_group_id
                    WHERE gm.parent_group_id = :group_id
                    ORDER BY g.name
                """),
                {"group_id": db_uuid(group_id)},
            )
            .mappings()
            .all()
        )
        return [{"id": str(to_uuid(r["id"])), "name": r["name"]} for r in rows]


@router.post("/admin/groups/{group_id}/children", status_code=201)
def admin_add_child_group(
    group_id: UUID,
    body: AddChildGroupRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, str]:
    require_admin(user)
    child_id = UUID(body.child_group_id)
    with request.app.state.engine.begin() as connection:
        for gid in (group_id, child_id):
            if (
                connection.execute(
                    sa.text("SELECT id FROM groups WHERE id = :id"),
                    {"id": db_uuid(gid)},
                ).first()
                is None
            ):
                raise HTTPException(status_code=404, detail="Group not found")
        auth_repo = AuthRepository(connection)
        if auth_repo._group_would_create_cycle(group_id, child_id):
            raise HTTPException(
                status_code=409,
                detail="Adding this group would create a circular membership.",
            )
        try:
            with connection.begin_nested():
                connection.execute(
                    sa.text(
                        "INSERT INTO group_memberships (parent_group_id, child_group_id)"
                        " VALUES (:parent, :child)"
                    ),
                    {"parent": db_uuid(group_id), "child": db_uuid(child_id)},
                )
        except sa.exc.IntegrityError:
            pass
        _audit_log(
            connection,
            user.sub,
            "add_child_group",
            "group",
            str(group_id),
            {"child_group_id": str(child_id)},
        )
        return {"group_id": str(group_id), "child_group_id": str(child_id)}


@router.delete("/admin/groups/{group_id}/children/{child_id}", status_code=204)
def admin_remove_child_group(
    group_id: UUID,
    child_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        group_row = connection.execute(
            sa.text("SELECT id FROM groups WHERE id = :id"),
            {"id": db_uuid(group_id)},
        ).first()
        if group_row is None:
            raise HTTPException(status_code=404, detail="Group not found")
        connection.execute(
            sa.text(
                "DELETE FROM group_memberships"
                " WHERE parent_group_id = :parent AND child_group_id = :child"
            ),
            {"parent": db_uuid(group_id), "child": db_uuid(child_id)},
        )
        _audit_log(
            connection,
            user.sub,
            "remove_child_group",
            "group",
            str(group_id),
            {"child_group_id": str(child_id)},
        )
