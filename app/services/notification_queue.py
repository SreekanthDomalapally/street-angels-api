import json
from typing import Any

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

QUEUE_KEY = "notifications:queue"
DLQ_KEY = "notifications:dlq"


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
        await self.connect()
        assert self._redis is not None
        await self._redis.rpush(QUEUE_KEY, json.dumps(payload))
        logger.info("notification_enqueued", extra={"type": payload.get("type")})

    async def enqueue_alert_created(
        self,
        *,
        alert_id: str,
        group_id: str,
        alert_type: str,
        latitude: float,
        longitude: float,
        recipient_user_ids: list[str],
    ) -> None:
        await self.enqueue(
            {
                "type": "alert_created",
                "priority": "high",
                "alert_id": alert_id,
                "group_id": group_id,
                "alert_type": alert_type,
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

    async def dequeue(self, timeout: int = 5) -> dict[str, Any] | None:
        await self.connect()
        assert self._redis is not None
        item = await self._redis.blpop(QUEUE_KEY, timeout=timeout)
        if not item:
            return None
        return json.loads(item[1])

    async def move_to_dlq(self, payload: dict[str, Any], error: str) -> None:
        await self.connect()
        assert self._redis is not None
        payload["error"] = error
        await self._redis.rpush(DLQ_KEY, json.dumps(payload))
