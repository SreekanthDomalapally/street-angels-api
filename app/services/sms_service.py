"""SMS delivery via Twilio (Phase 5). Push-first; SMS as fallback channel."""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SmsService:
    async def send(self, phone: str, body: str) -> bool:
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.info("sms_skipped_not_configured", extra={"phone": phone[:6] + "…"})
            return False
        try:
            import httpx

            url = (
                f"https://api.twilio.com/2010-04-01/Accounts/"
                f"{settings.twilio_account_sid}/Messages.json"
            )
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url,
                    data={
                        "To": phone,
                        "From": settings.twilio_from_number,
                        "Body": body,
                    },
                    auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                )
                if resp.status_code >= 400:
                    logger.error("sms_send_failed", extra={"status": resp.status_code})
                    return False
                return True
        except Exception as exc:
            logger.error("sms_send_error", extra={"error": str(exc)})
            return False


sms_service = SmsService()
