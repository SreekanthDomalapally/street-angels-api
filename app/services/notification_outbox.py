"""Transactional outbox for reliable notification delivery."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.notification_queue import NotificationQueue

logger = get_logger(__name__)


class NotificationOutbox:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.queue = NotificationQueue()

    async def enqueue_in_transaction(self, payload: dict[str, Any]) -> None:
        """Write outbox row in the current DB transaction (call before commit)."""
        from app.models import NotificationOutbox as NotificationOutboxRow

        row = NotificationOutboxRow(
            id=uuid.uuid4(),
            payload=payload,
            status="pending",
            attempts=0,
        )
        self.db.add(row)

    async def drain_pending(self, *, limit: int = 50) -> int:
        """Publish pending outbox rows to Redis. Returns count published."""
        from app.models import NotificationOutbox as NotificationOutboxRow

        result = await self.db.execute(
            select(NotificationOutboxRow)
            .where(NotificationOutboxRow.status == "pending")
            .order_by(NotificationOutboxRow.created_at.asc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        published = 0
        for row in rows:
            try:
                await self.queue.enqueue(row.payload)
                row.status = "published"
                row.published_at = datetime.now(UTC)
                published += 1
            except Exception as exc:
                row.attempts += 1
                row.last_error = str(exc)[:500]
                logger.warning(
                    "outbox_publish_failed",
                    extra={"outbox_id": str(row.id), "error": row.last_error},
                )
        if published:
            await self.db.flush()
        return published

    async def mark_failed(self, outbox_id: uuid.UUID, error: str) -> None:
        from app.models import NotificationOutbox as NotificationOutboxRow

        await self.db.execute(
            update(NotificationOutboxRow)
            .where(NotificationOutboxRow.id == outbox_id)
            .values(
                status="failed",
                attempts=NotificationOutboxRow.attempts + 1,
                last_error=error[:500],
            )
        )
