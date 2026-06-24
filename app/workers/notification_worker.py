import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger
from app.db.session import get_engine
from app.models import AlertRecipient, DeviceToken
from app.services.expo_push_service import ExpoPushService
from app.services.notification_outbox import NotificationOutbox
from app.services.notification_queue import NotificationQueue

logger = get_logger(__name__)


class NotificationWorker:
    def __init__(self) -> None:
        self.queue = NotificationQueue()
        self.push = ExpoPushService()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_heartbeat: datetime | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        recovered = await self.queue.recover_processing()
        if recovered:
            logger.warning("notification_processing_recovered", extra={"count": recovered})
        self._task = asyncio.create_task(self._run())
        logger.info("notification_worker_started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.queue.close()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def task_alive(self) -> bool:
        return self._task is not None and not self._task.done()

    def status_snapshot(self) -> dict[str, bool | str | None]:
        return {
            "running": self.is_running,
            "task_alive": self.task_alive,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
        }

    async def _run(self) -> None:
        while self._running:
            try:
                self._last_heartbeat = datetime.now(UTC)
                await self._drain_outbox()
                item = await self.queue.dequeue(timeout=2)
                if item:
                    payload, raw = item
                    await self._process(payload, raw)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("notification_worker_error", extra={"error": str(exc)})
                await asyncio.sleep(1)

    async def _drain_outbox(self) -> None:
        engine = get_engine()
        if not engine:
            return
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            outbox = NotificationOutbox(session)
            published = await outbox.drain_pending()
            if published:
                await session.commit()
                logger.info("outbox_drained", extra={"published": published})

    async def _process(self, payload: dict[str, Any], raw: str) -> None:
        try:
            msg_type = payload.get("type")
            stale: list[str] = []
            if msg_type == "alert_created":
                tokens = await self._tokens_for_users(payload.get("recipient_user_ids", []))
                stale = await self.push.send_alert(tokens, payload)
                await self._mark_recipients_delivered(
                    payload.get("alert_id"),
                    payload.get("recipient_user_ids", []),
                    success=True,
                )
            elif msg_type == "alert_response":
                tokens = await self._tokens_for_users([payload.get("creator_id", "")])
                stale = await self.push.send_to_tokens(
                    tokens,
                    title="Alert response",
                    body=f"{payload.get('responder_name')} — {payload.get('response_type')}",
                    data={
                        "type": "responder_update",
                        "alert_id": str(payload.get("alert_id", "")),
                        "response_type": str(payload.get("response_type", "")),
                    },
                    channel_id="responder",
                    high_priority=True,
                )
            elif msg_type == "trip_started":
                tokens = await self._tokens_for_users(payload.get("recipient_user_ids", []))
                stale = await self.push.send_to_tokens(
                    tokens,
                    title="Trip watch started",
                    body=f"{payload.get('traveler_name')} started {payload.get('label')}",
                    data={
                        "type": "group_update",
                        "trip_id": str(payload.get("trip_id", "")),
                        "group_id": str(payload.get("group_id", "")),
                    },
                    channel_id="groups",
                    high_priority=False,
                )
            elif msg_type == "trip_arrived":
                tokens = await self._tokens_for_users(payload.get("recipient_user_ids", []))
                stale = await self.push.send_to_tokens(
                    tokens,
                    title="Arrived safely",
                    body=f"{payload.get('traveler_name')} reached {payload.get('destination_label')}",
                    data={
                        "type": "check_in",
                        "trip_id": str(payload.get("trip_id", "")),
                        "group_id": str(payload.get("group_id", "")),
                    },
                    channel_id="groups",
                    high_priority=True,
                )

            await self._remove_stale_tokens(stale)
            await self.queue.ack(raw)
        except Exception as exc:
            await self.queue.retry_or_dlq(payload, raw, str(exc))
            if payload.get("type") == "alert_created":
                await self._mark_recipients_delivered(
                    payload.get("alert_id"),
                    payload.get("recipient_user_ids", []),
                    success=False,
                    error=str(exc),
                )
            logger.error("notification_process_failed", extra={"error": str(exc)})

    async def _mark_recipients_delivered(
        self,
        alert_id: str | None,
        user_ids: list[str],
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        if not alert_id or not user_ids:
            return
        engine = get_engine()
        if not engine:
            return
        factory = async_sessionmaker(engine, expire_on_commit=False)
        ids = [UUID(uid) for uid in user_ids if uid]
        if not ids:
            return
        async with factory() as session:
            await session.execute(
                update(AlertRecipient)
                .where(
                    AlertRecipient.alert_id == UUID(alert_id),
                    AlertRecipient.user_id.in_(ids),
                )
                .values(
                    notified=True,
                    notified_at=datetime.now(UTC),
                    delivery_status="delivered" if success else "failed",
                    delivery_error=error[:500] if error else None,
                )
            )
            await session.commit()

    async def _remove_stale_tokens(self, tokens: list[str]) -> None:
        if not tokens:
            return
        engine = get_engine()
        if not engine:
            return
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(delete(DeviceToken).where(DeviceToken.token.in_(tokens)))
            await session.commit()
        logger.info("push_tokens_removed", extra={"count": len(tokens)})

    async def _tokens_for_users(self, user_ids: list[str]) -> list[str]:
        engine = get_engine()
        if not engine:
            return []
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            ids = [UUID(uid) for uid in user_ids if uid]
            if not ids:
                return []
            result = await session.execute(
                select(DeviceToken.token).where(DeviceToken.user_id.in_(ids))
            )
            return list(result.scalars().all())


notification_worker = NotificationWorker()
