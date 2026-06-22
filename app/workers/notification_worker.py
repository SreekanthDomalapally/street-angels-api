import asyncio
from typing import Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import get_engine
from app.models import DeviceToken
from app.services.fcm_service import FCMService
from app.services.notification_queue import NotificationQueue

logger = get_logger(__name__)


class NotificationWorker:
    def __init__(self) -> None:
        self.queue = NotificationQueue()
        self.fcm = FCMService()
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
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

    async def _run(self) -> None:
        while self._running:
            try:
                payload = await self.queue.dequeue(timeout=2)
                if payload:
                    await self._process(payload)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("notification_worker_error", extra={"error": str(exc)})
                await asyncio.sleep(1)

    async def _process(self, payload: dict[str, Any]) -> None:
        try:
            msg_type = payload.get("type")
            if msg_type == "alert_created":
                tokens = await self._tokens_for_users(payload.get("recipient_user_ids", []))
                await self.fcm.send_alert(tokens, payload)
            elif msg_type == "alert_response":
                tokens = await self._tokens_for_users([payload.get("creator_id", "")])
                await self.fcm.send_to_tokens(
                    tokens,
                    title="Alert response",
                    body=f"{payload.get('responder_name')} — {payload.get('response_type')}",
                    data={k: str(v) for k, v in payload.items()},
                    high_priority=True,
                )
            elif msg_type == "trip_started":
                tokens = await self._tokens_for_users(payload.get("recipient_user_ids", []))
                await self.fcm.send_to_tokens(
                    tokens,
                    title="Trip watch started",
                    body=f"{payload.get('traveler_name')} started {payload.get('label')}",
                    data={
                        "type": "group_update",
                        "trip_id": str(payload.get("trip_id", "")),
                        "group_id": str(payload.get("group_id", "")),
                    },
                    high_priority=False,
                )
            elif msg_type == "trip_arrived":
                tokens = await self._tokens_for_users(payload.get("recipient_user_ids", []))
                await self.fcm.send_to_tokens(
                    tokens,
                    title="Arrived safely",
                    body=f"{payload.get('traveler_name')} reached {payload.get('destination_label')}",
                    data={
                        "type": "check_in",
                        "trip_id": str(payload.get("trip_id", "")),
                        "group_id": str(payload.get("group_id", "")),
                    },
                    high_priority=True,
                )
        except Exception as exc:
            await self.queue.move_to_dlq(payload, str(exc))
            logger.error("notification_process_failed", extra={"error": str(exc)})

    async def _tokens_for_users(self, user_ids: list[str]) -> list[str]:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        engine = get_engine()
        if not engine:
            return []
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            from uuid import UUID

            ids = [UUID(uid) for uid in user_ids if uid]
            if not ids:
                return []
            result = await session.execute(
                select(DeviceToken.token).where(DeviceToken.user_id.in_(ids))
            )
            return list(result.scalars().all())


notification_worker = NotificationWorker()
