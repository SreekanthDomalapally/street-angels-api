"""JWT access-token revocation via Redis denylist."""

from __future__ import annotations

from datetime import UTC, datetime

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

DENY_PREFIX = "jwt:deny:"


class TokenRevocationService:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)

    async def revoke(self, jti: str, *, expires_at: datetime) -> None:
        if not jti:
            return
        try:
            await self.connect()
            assert self._redis is not None
            ttl = max(int((expires_at - datetime.now(UTC)).total_seconds()), 60)
            await self._redis.setex(f"{DENY_PREFIX}{jti}", ttl, "1")
        except Exception as exc:
            logger.warning("token_revoke_failed", extra={"error": str(exc)})

    async def is_revoked(self, jti: str | None) -> bool:
        if not jti:
            return False
        try:
            await self.connect()
            assert self._redis is not None
            return bool(await self._redis.exists(f"{DENY_PREFIX}{jti}"))
        except Exception:
            return False


token_revocation = TokenRevocationService()
