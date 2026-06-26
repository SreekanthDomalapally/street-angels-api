"""Development/admin SOS delivery debug endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, require_admin
from app.core.exceptions import ForbiddenError
from app.db.session import get_db
from app.models import DeviceToken, User
from app.services.expo_push_service import ExpoPushService
from app.services.sos_delivery_debug import build_alert_delivery_report, build_routing_preview

router = APIRouter(prefix="/debug", tags=["debug"])


def _require_debug_tools(user: User) -> None:
  """Routing preview and test push are admin-only in production."""
  if not settings.is_production:
    return
  if user.is_admin or user.email.lower() in settings.admin_email_set:
    return
  raise ForbiddenError("Debug tools require admin access in production")


@router.get("/alerts/{alert_id}/delivery")
async def alert_delivery_report(
    alert_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    report = await build_alert_delivery_report(db, user, alert_id)
    from app.services.notification_health import collect_notification_health

    health = await collect_notification_health()
    report["notification_queue_status"] = health.get("checks", {}).get("redis_queue", {})
    report["push_send_status"] = health.get("checks", {}).get("push_pipeline", {})
    report["delivery_status"] = {
        "delivered": sum(
            1 for r in report.get("selected_recipients", []) if r.get("delivery_status") == "delivered"
        ),
        "failed": sum(
            1 for r in report.get("selected_recipients", []) if r.get("delivery_status") == "failed"
        ),
        "pending": sum(
            1 for r in report.get("selected_recipients", []) if r.get("delivery_status") == "pending"
        ),
    }
    return report


@router.get("/sos/routing-preview")
async def sos_routing_preview(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    emergency_type: str = Query(..., alias="emergency_type"),
    group_id: UUID = Query(..., alias="group_id"),
) -> dict:
    _require_debug_tools(user)
    return await build_routing_preview(db, user, emergency_type=emergency_type, group_id=group_id)


@router.post("/push/test-me", status_code=204)
async def push_test_me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Send a test push notification to the current user's registered device tokens."""
    _require_debug_tools(user)
    result = await db.execute(select(DeviceToken.token).where(DeviceToken.user_id == user.id))
    tokens = [row[0] for row in result.all()]
    if not tokens:
        raise ForbiddenError("No device tokens registered for your account")
    push = ExpoPushService()
    await push.send_to_tokens(
        tokens,
        title="YouHoo Alert test",
        body="Push delivery is working.",
        data={"type": "sos_alert", "is_own_alert": True},
        channel_id="emergency",
        high_priority=True,
    )


@router.get("/status")
async def debug_status(
    _admin: Annotated[User, Depends(require_admin)],
) -> dict:
    return {
        "environment": settings.environment,
        "push_enabled": settings.push_enabled,
        "debug_mode": settings.debug,
    }
