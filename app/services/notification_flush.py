"""Flush SOS notification outbox immediately after alert commit."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


async def flush_sos_notifications() -> int:
    """Publish pending outbox rows to Redis after the alert transaction commits."""
    from app.workers.notification_worker import notification_worker

    try:
        published = await notification_worker.drain_outbox_once()
        if published:
            logger.info("NOTIFICATION_FLUSH_AFTER_SOS", extra={"published": published})
        return published
    except Exception as exc:
        logger.error("NOTIFICATION_FLUSH_FAILED", extra={"error": str(exc)})
        return 0
