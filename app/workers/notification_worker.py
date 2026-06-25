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
                item = await self.queue.dequeue(timeout=0)
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

    async def drain_outbox_once(self) -> int:
        engine = get_engine()
        if not engine:
            return 0
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            outbox = NotificationOutbox(session)
            published = await outbox.drain_pending()
            if published:
                await session.commit()
                logger.info("outbox_drained_immediate", extra={"published": published})
            return published

    async def _process(self, payload: dict[str, Any], raw: str) -> None:
        try:
            msg_type = payload.get("type")
            payload["notification_sent_at"] = datetime.now(UTC).isoformat()
            if payload.get("alert_created_at") and payload.get("notification_queued_at"):
                try:
                    created = datetime.fromisoformat(str(payload["alert_created_at"]))
                    queued = datetime.fromisoformat(str(payload["notification_queued_at"]))
                    sent = datetime.now(UTC)
                    logger.info(
                        "alert_notification_timing",
                        extra={
                            "alert_id": payload.get("alert_id"),
                            "create_to_queue_ms": int((queued - created).total_seconds() * 1000),
                            "queue_to_send_ms": int((sent - queued).total_seconds() * 1000),
                            "create_to_send_ms": int((sent - created).total_seconds() * 1000),
                        },
                    )
                except (TypeError, ValueError):
                    pass
            stale: list[str] = []
            if msg_type == "alert_created":
                recipient_ids = [str(uid) for uid in payload.get("recipient_user_ids", []) if uid]
                tokens_by_user = await self._tokens_by_user(recipient_ids)
                users_with_tokens = [uid for uid in recipient_ids if tokens_by_user.get(uid)]
                users_without_tokens = [uid for uid in recipient_ids if not tokens_by_user.get(uid)]
                all_tokens = [token for tokens in tokens_by_user.values() for token in tokens]
                log_extra = {
                    "correlation_id": payload.get("correlation_id"),
                    "alert_id": payload.get("alert_id"),
                    "sender_user_id": payload.get("sender_user_id"),
                    "recipient_count": len(recipient_ids),
                    "recipient_user_ids": recipient_ids,
                }
                if not all_tokens:
                    logger.warning(
                        "NOTIFICATION_FAILED",
                        extra={
                            **log_extra,
                            "error": "no_device_tokens",
                        },
                    )
                    await self._mark_recipients_delivered(
                        payload.get("alert_id"),
                        recipient_ids,
                        success=False,
                        error="no_device_token",
                    )
                else:
                    try:
                        stale = await self.push.send_alert(all_tokens, payload)
                        await self._mark_recipients_delivered(
                            payload.get("alert_id"),
                            users_with_tokens,
                            success=True,
                        )
                        if users_without_tokens:
                            await self._mark_recipients_delivered(
                                payload.get("alert_id"),
                                users_without_tokens,
                                success=False,
                                error="no_device_token",
                            )
                        logger.info(
                            "NOTIFICATION_SENT",
                            extra={
                                **log_extra,
                                "token_count": len(all_tokens),
                            },
                        )
                    except Exception as push_exc:
                        await self._mark_recipients_delivered(
                            payload.get("alert_id"),
                            users_with_tokens,
                            success=False,
                            error=str(push_exc),
                        )
                        if users_without_tokens:
                            await self._mark_recipients_delivered(
                                payload.get("alert_id"),
                                users_without_tokens,
                                success=False,
                                error="no_device_token",
                            )
                        logger.error(
                            "NOTIFICATION_FAILED",
                            extra={**log_extra, "error": str(push_exc)},
                        )
                        raise
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
            logger.error(
                "NOTIFICATION_FAILED",
                extra={
                    "correlation_id": payload.get("correlation_id"),
                    "alert_id": payload.get("alert_id"),
                    "sender_user_id": payload.get("sender_user_id"),
                    "recipient_count": len(payload.get("recipient_user_ids", []) or []),
                    "error": str(exc),
                },
            )

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

    async def _tokens_by_user(self, user_ids: list[str]) -> dict[str, list[str]]:
        engine = get_engine()
        if not engine:
            return {}
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            ids = [UUID(uid) for uid in user_ids if uid]
            if not ids:
                return {}
            result = await session.execute(
                select(DeviceToken.user_id, DeviceToken.token).where(DeviceToken.user_id.in_(ids))
            )
            tokens_by_user: dict[str, list[str]] = {}
            for user_id, token in result.all():
                key = str(user_id)
                tokens_by_user.setdefault(key, []).append(token)
            return tokens_by_user

    async def _tokens_for_users(self, user_ids: list[str]) -> list[str]:
        tokens_by_user = await self._tokens_by_user(user_ids)
        return [token for tokens in tokens_by_user.values() for token in tokens]


notification_worker = NotificationWorker()
