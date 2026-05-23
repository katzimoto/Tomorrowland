"""Admin routes for RabbitMQ queue observability."""

from __future__ import annotations

import json
import logging
import urllib.request
from base64 import b64encode
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

_QUEUE_NAMES = [
    "document.parse.requested",
    "document.translate.requested",
    "document.embed.requested",
    "document.index.requested",
    "document.intelligence.requested",
    "document.alert.requested",
]


def _mgmt_get(settings: Any, path: str) -> list[dict[str, Any]] | None:
    """Call RabbitMQ management API and return the parsed JSON response."""
    try:
        user = getattr(settings, "rabbitmq_user", "guest")
        password = getattr(settings, "rabbitmq_pass", "guest")
        url = f"http://rabbitmq:15672/api/{path.lstrip('/')}"
        req = urllib.request.Request(url)
        auth = b64encode(f"{user}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {auth}")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())  # type: ignore[no-any-return]
    except Exception as exc:
        logger.warning("RabbitMQ management API error: path=%s error=%s", path, exc)
        return None


@router.get("/admin/rabbit/queues")
def admin_rabbit_queues(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    settings = request.app.state.settings

    all_queues = _mgmt_get(settings, "queues")
    if all_queues is None:
        return {"queues": [], "error": "RabbitMQ management API unreachable"}

    by_name: dict[str, dict[str, Any]] = {}
    for q in all_queues:
        by_name[q["name"]] = q

    result: list[dict[str, Any]] = []
    for name in _QUEUE_NAMES:
        q = by_name.get(name, {})
        dlq_name = name.replace("requested", "dead")
        dlq = by_name.get(dlq_name, {})
        result.append(
            {
                "queue": name,
                "depth": q.get("messages_ready", 0) + q.get("messages_unacknowledged", 0),
                "consumers": q.get("consumers", 0),
                "dlq": dlq_name,
                "dlq_depth": dlq.get("messages_ready", 0) + dlq.get("messages_unacknowledged", 0),
            }
        )

    return {"queues": result}
