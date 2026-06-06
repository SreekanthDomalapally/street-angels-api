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
from app.repositories.alert_repository import AlertRepository
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=AlertOut)
@limiter.limit(settings.alert_rate_limit)
async def create_alert(
    request: Request,
    body: AlertCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertOut:
    created = await AlertService(db).create(user, body)
    alert = await AlertRepository(db).get_by_id(created.id) or created
    return AlertOut.model_validate(alert)


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertOut:
    alert = await AlertService(db).get(user, alert_id)
    return AlertOut.model_validate(alert)


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
    return AlertOut.model_validate(alert)
