"""Redis-backed per-user rate limiting for sensitive endpoints."""

from __future__ import annotations

import time

import redis.asyncio as redis

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisRateLimiter:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Raise ValidationError if the key exceeded limit within the window."""
        try:
            await self.connect()
            assert self._redis is not None
            now = int(time.time())
            bucket = f"rl:{key}:{now // window_seconds}"
            count = await self._redis.incr(bucket)
            if count == 1:
                await self._redis.expire(bucket, window_seconds + 1)
            if count > limit:
                raise ValidationError("Too many requests. Please wait and try again.")
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning("rate_limit_skipped", extra={"key": key, "error": str(exc)})


redis_rate_limiter = RedisRateLimiter()
