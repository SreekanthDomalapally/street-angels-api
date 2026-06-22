from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.enums import TripStatus
from app.models import Trip


class TripRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, trip: Trip) -> Trip:
        self.db.add(trip)
        await self.db.flush()
        await self.db.refresh(trip)
        return trip

    async def get_by_id(self, trip_id: UUID) -> Trip | None:
        result = await self.db.execute(
            select(Trip)
            .options(selectinload(Trip.group), selectinload(Trip.traveler))
            .where(Trip.id == trip_id)
        )
        return result.scalar_one_or_none()

    async def get_active_for_traveler(self, traveler_user_id: UUID) -> Trip | None:
        result = await self.db.execute(
            select(Trip)
            .options(selectinload(Trip.group), selectinload(Trip.traveler))
            .where(
                Trip.traveler_user_id == traveler_user_id,
                Trip.status == TripStatus.ACTIVE.value,
            )
            .order_by(Trip.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_active_for_group(self, group_id: UUID) -> list[Trip]:
        result = await self.db.execute(
            select(Trip)
            .options(selectinload(Trip.group), selectinload(Trip.traveler))
            .where(Trip.group_id == group_id, Trip.status == TripStatus.ACTIVE.value)
            .order_by(Trip.started_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, trip: Trip) -> Trip:
        await self.db.flush()
        await self.db.refresh(trip)
        return trip
