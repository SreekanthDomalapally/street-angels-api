from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Alert, AlertEvent, AlertLocationUpdate, AlertResponse


class AlertRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, alert_id: UUID) -> Alert | None:
        result = await self.db.execute(
            select(Alert)
            .options(selectinload(Alert.responses), selectinload(Alert.location_updates))
            .where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def create(self, alert: Alert) -> Alert:
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)
        return alert

    async def add_response(self, response: AlertResponse) -> AlertResponse:
        self.db.add(response)
        await self.db.flush()
        await self.db.refresh(response)
        return response

    async def get_response(self, alert_id: UUID, user_id: UUID) -> AlertResponse | None:
        result = await self.db.execute(
            select(AlertResponse).where(
                AlertResponse.alert_id == alert_id, AlertResponse.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def add_location(self, update: AlertLocationUpdate) -> AlertLocationUpdate:
        self.db.add(update)
        await self.db.flush()
        await self.db.refresh(update)
        return update

    async def log_event(self, event: AlertEvent) -> AlertEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_active_for_user(self, user_id: UUID) -> list[Alert]:
        result = await self.db.execute(
            select(Alert)
            .where(Alert.created_by == user_id, Alert.status == "active")
            .order_by(Alert.created_at.desc())
        )
        return list(result.scalars().all())
