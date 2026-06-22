from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import LocationUpdateRequest, TripCreateRequest, TripOut
from app.services.trip_service import TripService

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripOut, status_code=status.HTTP_201_CREATED)
async def create_trip(
    body: TripCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripOut:
    return await TripService(db).create(user, body)


@router.get("/active/mine", response_model=TripOut)
async def get_active_trip_mine(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripOut:
    return await TripService(db).get_active_mine(user)


@router.get("/{trip_id}", response_model=TripOut)
async def get_trip(
    trip_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripOut:
    return await TripService(db).get(user, trip_id)


@router.post("/{trip_id}/location", response_model=TripOut)
async def update_trip_location(
    trip_id: UUID,
    body: LocationUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripOut:
    return await TripService(db).update_location(user, trip_id, body)


@router.post("/{trip_id}/arrive", response_model=TripOut)
async def arrive_trip(
    trip_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripOut:
    return await TripService(db).arrive(user, trip_id)


@router.post("/{trip_id}/end", response_model=TripOut)
async def end_trip(
    trip_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TripOut:
    return await TripService(db).end(user, trip_id)
