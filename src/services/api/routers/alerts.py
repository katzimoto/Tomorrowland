from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from services.alerts.models import SubscriptionCreateRequest, SubscriptionUpdateRequest
from services.alerts.repository import AlertRepository
from services.alerts.service import AlertMatcher
from services.api._helpers import (
    _notification_response,
    _subscription_response,
    default_alert_threshold,
    require_subscriptions_enabled,
)
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.permissions.enforcer import require_admin
from services.pipeline.jobs import PipelineJobRepository
from services.search.factory import build_encoder
from shared.db import to_uuid

router = APIRouter(tags=["alerts"])


@router.get("/subscriptions")
def list_subscriptions(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> list[dict[str, Any]]:
    with request.app.state.engine.begin() as connection:
        require_subscriptions_enabled(connection, request.app.state.settings)
        repo = AlertRepository(connection)
        return [_subscription_response(row) for row in repo.list_subscriptions(user.sub)]


@router.post("/subscriptions", status_code=201)
def create_subscription(
    body: SubscriptionCreateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        require_subscriptions_enabled(connection, request.app.state.settings)
        repo = AlertRepository(connection)
        row = repo.create_subscription(
            user_id=user.sub,
            name=body.name,
            query=body.query,
            similarity_threshold=body.similarity_threshold,
            enabled=body.enabled,
        )
        request.app.state.metrics.subscriptions_total.labels("create", "success").inc()
        return _subscription_response(row)


@router.put("/subscriptions/{subscription_id}")
def update_subscription(
    subscription_id: UUID,
    body: SubscriptionUpdateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        require_subscriptions_enabled(connection, request.app.state.settings)
        repo = AlertRepository(connection)
        subscription = repo.get_subscription(subscription_id)
        if subscription is None or to_uuid(subscription["user_id"]) != user.sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        updated = repo.update_subscription(
            subscription_id,
            name=body.name,
            query=body.query,
            similarity_threshold=body.similarity_threshold,
            enabled=body.enabled,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        request.app.state.metrics.subscriptions_total.labels("update", "success").inc()
        return _subscription_response(updated)


@router.delete("/subscriptions/{subscription_id}", status_code=204)
def delete_subscription(
    subscription_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> None:
    with request.app.state.engine.begin() as connection:
        require_subscriptions_enabled(connection, request.app.state.settings)
        repo = AlertRepository(connection)
        subscription = repo.get_subscription(subscription_id)
        if subscription is None or to_uuid(subscription["user_id"]) != user.sub:
            raise HTTPException(status_code=404, detail="Subscription not found")
        repo.delete_subscription(subscription_id)
        request.app.state.metrics.subscriptions_total.labels("delete", "success").inc()


@router.get("/notifications")
def list_notifications(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    unread_only: bool = True,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    with request.app.state.engine.begin() as connection:
        require_subscriptions_enabled(connection, request.app.state.settings)
        # Compute effective groups for non-admin callers so that notifications
        # referencing documents the user has since lost access to are filtered out.
        if user.is_admin:
            effective_groups: list[UUID] = []
        else:
            auth_repo = AuthRepository(connection)
            effective_groups = list(
                set(user.groups) | set(auth_repo.get_effective_group_ids(user.groups))
            )
        repo = AlertRepository(connection)
        return [
            _notification_response(row)
            for row in repo.list_notifications(
                user.sub,
                unread_only=unread_only,
                group_ids=effective_groups,
                allow_all=user.is_admin,
                limit=limit,
                offset=offset,
            )
        ]


@router.put("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    with request.app.state.engine.begin() as connection:
        require_subscriptions_enabled(connection, request.app.state.settings)
        repo = AlertRepository(connection)
        notification = repo.get_notification(notification_id)
        if notification is None or to_uuid(notification["user_id"]) != user.sub:
            raise HTTPException(status_code=404, detail="Notification not found")
        updated = repo.mark_notification_read(notification_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        request.app.state.metrics.notifications_total.labels("read", "success").inc()
        return {
            "id": str(to_uuid(updated["id"])),
            "read": bool(updated["read"]),
        }


@router.post("/admin/alerts/{document_id}/trigger")
def trigger_alert_matching(
    document_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        require_subscriptions_enabled(connection, request.app.state.settings)
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.get_by_id(document_id)
        if doc is None or doc.path is None:
            raise HTTPException(status_code=404, detail="Document not found")

        payload = PipelineJobRepository(connection).get_payload(document_id)
        content = (payload.get("content_text", "") if payload else None) or ""
        matcher = AlertMatcher(
            repository=AlertRepository(connection),
            encoder=build_encoder(
                request.app.state.settings,
                resolver=getattr(request.app.state, "task_default_resolver", None),
            ),
            default_threshold=default_alert_threshold(connection),
        )
        created = matcher.match_document(doc, content)
        return {
            "document_id": str(document_id),
            "notifications_created": created,
        }
