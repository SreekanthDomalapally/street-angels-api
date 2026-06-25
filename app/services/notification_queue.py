import json
from typing import Any

import redis.asyncio as redis

from app.core.config import settings
from app.core.log_extra import safe_extra
from app.core.logging import get_logger

logger = get_logger(__name__)

QUEUE_KEY = "notifications:queue"
PROCESSING_KEY = "notifications:processing"
DLQ_KEY = "notifications:dlq"
MAX_DELIVERY_ATTEMPTS = 3


class NotificationQueue:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def enqueue(self, payload: dict[str, Any]) -> None:
        try:
            await self.connect()
            assert self._redis is not None
            await self._redis.rpush(QUEUE_KEY, json.dumps(payload))
            log_extra = safe_extra(
                type=payload.get("type"),
                alert_id=payload.get("alert_id"),
                correlation_id=payload.get("correlation_id"),
                sender_user_id=payload.get("sender_user_id"),
                recipient_count=payload.get("recipient_count"),
                recipient_user_ids=payload.get("recipient_user_ids"),
            )
            if payload.get("type") == "alert_created":
                logger.info("NOTIFICATION_QUEUED", extra=log_extra)
            else:
                logger.info("notification_enqueued", extra=log_extra)
        except Exception as exc:
            # Alerts must succeed even when Redis/FCM is unavailable (e.g. Railway without Redis).
            logger.warning(
                "notification_enqueue_skipped",
                extra={"type": payload.get("type"), "error": str(exc)},
            )

    async def enqueue_alert_created(
        self,
        *,
        alert_id: str,
        group_id: str,
        alert_type: str,
        latitude: float,
        longitude: float,
        recipient_user_ids: list[str],
        sender_name: str | None = None,
    ) -> None:
        await self.enqueue(
            {
                "type": "alert_created",
                "priority": "high",
                "alert_id": alert_id,
                "group_id": group_id,
                "alert_type": alert_type,
                "sender_name": sender_name,
                "latitude": latitude,
                "longitude": longitude,
                "recipient_user_ids": recipient_user_ids,
            }
        )

    async def enqueue_alert_response(
        self,
        *,
        alert_id: str,
        creator_id: str,
        responder_name: str,
        response_type: str,
    ) -> None:
        await self.enqueue(
            {
                "type": "alert_response",
                "priority": "high",
                "alert_id": alert_id,
                "creator_id": creator_id,
                "responder_name": responder_name,
                "response_type": response_type,
            }
        )

    async def enqueue_trip_started(
        self,
        *,
        trip_id: str,
        group_id: str,
        traveler_name: str,
        label: str,
        recipient_user_ids: list[str],
    ) -> None:
        await self.enqueue(
            {
                "type": "trip_started",
                "priority": "default",
                "trip_id": trip_id,
                "group_id": group_id,
                "traveler_name": traveler_name,
                "label": label,
                "recipient_user_ids": recipient_user_ids,
            }
        )

    async def enqueue_trip_arrived(
        self,
        *,
        trip_id: str,
        group_id: str,
        traveler_name: str,
        destination_label: str,
        recipient_user_ids: list[str],
    ) -> None:
        await self.enqueue(
            {
                "type": "trip_arrived",
                "priority": "high",
                "trip_id": trip_id,
                "group_id": group_id,
                "traveler_name": traveler_name,
                "destination_label": destination_label,
                "recipient_user_ids": recipient_user_ids,
            }
        )

    async def dequeue(self, timeout: int = 5) -> tuple[dict[str, Any], str] | None:
        """At-least-once dequeue via BRPOPLPUSH into a processing list."""
        await self.connect()
        assert self._redis is not None
        raw = await self._redis.brpoplpush(QUEUE_KEY, PROCESSING_KEY, timeout=timeout)
        if not raw:
            return None
        return json.loads(raw), raw

    async def ack(self, raw: str) -> None:
        await self.connect()
        assert self._redis is not None
        await self._redis.lrem(PROCESSING_KEY, 1, raw)

    async def recover_processing(self) -> int:
        """Move orphaned processing entries back to the queue (worker restart)."""
        await self.connect()
        assert self._redis is not None
        moved = 0
        while True:
            raw = await self._redis.rpoplpush(PROCESSING_KEY, QUEUE_KEY)
            if not raw:
                break
            moved += 1
        return moved

    async def retry_or_dlq(self, payload: dict[str, Any], raw: str, error: str) -> None:
        await self.ack(raw)
        attempts = int(payload.get("_attempts", 0)) + 1
        payload["_attempts"] = attempts
        if attempts >= MAX_DELIVERY_ATTEMPTS:
            await self.move_to_dlq(payload, error)
        else:
            await self.enqueue(payload)

    async def move_to_dlq(self, payload: dict[str, Any], error: str) -> None:
        await self.connect()
        assert self._redis is not None
        payload["error"] = error
        await self._redis.rpush(DLQ_KEY, json.dumps(payload))

    async def list_dlq(self, limit: int = 50) -> list[dict[str, Any]]:
        await self.connect()
        assert self._redis is not None
        raw = await self._redis.lrange(DLQ_KEY, 0, limit - 1)
        entries: list[dict[str, Any]] = []
        for item in raw:
            try:
                entries.append(json.loads(item))
            except (ValueError, TypeError):
                entries.append({"error": "unparseable", "raw": item})
        return entries

    async def requeue_dlq(self) -> int:
        """Move all DLQ entries back to the main queue for retry. Returns count moved."""
        await self.connect()
        assert self._redis is not None
        moved = 0
        while True:
            item = await self._redis.lpop(DLQ_KEY)
            if item is None:
                break
            try:
                payload = json.loads(item)
                payload.pop("error", None)
                await self._redis.rpush(QUEUE_KEY, json.dumps(payload))
                moved += 1
            except (ValueError, TypeError):
                continue
        return moved

    async def clear_dlq(self) -> int:
        await self.connect()
        assert self._redis is not None
        count = int(await self._redis.llen(DLQ_KEY))
        await self._redis.delete(DLQ_KEY)
        return count

    async def health_check(self) -> dict[str, Any]:
        """Ping Redis and return queue depths for diagnostics."""
        import time
        from urllib.parse import urlparse

        host = urlparse(settings.redis_url).hostname or "unknown"
        try:
            await self.connect()
            assert self._redis is not None
            started = time.perf_counter()
            await self._redis.ping()
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            pending = int(await self._redis.llen(QUEUE_KEY))
            processing = int(await self._redis.llen(PROCESSING_KEY))
            dlq = int(await self._redis.llen(DLQ_KEY))
            dlq_last_error: str | None = None
            dlq_last_type: str | None = None
            if dlq > 0:
                raw = await self._redis.lindex(DLQ_KEY, -1)
                if raw:
                    try:
                        entry = json.loads(raw)
                        dlq_last_error = str(entry.get("error"))[:300]
                        dlq_last_type = entry.get("type")
                    except (ValueError, TypeError):
                        dlq_last_error = "unparseable DLQ entry"
            return {
                "ok": True,
                "host": host,
                "latency_ms": latency_ms,
                "queue_pending": pending,
                "processing": processing,
                "dlq": dlq,
                "dlq_last_error": dlq_last_error,
                "dlq_last_type": dlq_last_type,
                "error": None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "host": host,
                "latency_ms": None,
                "queue_pending": None,
                "dlq": None,
                "error": str(exc),
            }
