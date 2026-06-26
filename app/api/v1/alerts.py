from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models import User
from app.schemas import (
    AlertCreateRequest,
    AlertOut,
    AlertResponseItem,
    AlertResponseRequest,
    LocationUpdateRequest,
)
from app.core.redis_rate_limit import redis_rate_limiter
from app.services.alert_serializer import serialize_alert, serialize_alerts
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AlertOut]:
    alerts = await AlertService(db).list_for_user(user)
    return await serialize_alerts(db, alerts, viewer=user)


@router.post("", response_model=AlertOut)
@limiter.limit(settings.alert_rate_limit)
async def create_alert(
    request: Request,
    body: AlertCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertOut:
    await redis_rate_limiter.check(f"sos:{user.id}", limit=5, window_seconds=60)
    created = await AlertService(db).create(user, body)
    return await serialize_alert(db, created, viewer=user)


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertOut:
    alert = await AlertService(db).get(user, alert_id)
    return await serialize_alert(db, alert, viewer=user)


@router.post("/{alert_id}/responses", response_model=AlertResponseItem)
async def respond_to_alert(
    alert_id: UUID,
    body: AlertResponseRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertResponseItem:
    response = await AlertService(db).respond(user, alert_id, body)
    return AlertResponseItem.model_validate(response)


@router.post("/{alert_id}/location")
async def update_location(
    alert_id: UUID,
    body: LocationUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    update = await AlertService(db).update_location(user, alert_id, body)
    return {
        "latitude": update.latitude,
        "longitude": update.longitude,
        "recorded_at": update.recorded_at.isoformat(),
    }


@router.post("/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(
    alert_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertOut:
    alert = await AlertService(db).resolve(user, alert_id)
    return await serialize_alert(db, alert, viewer=user)
