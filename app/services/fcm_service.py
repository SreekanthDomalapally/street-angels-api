import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class FCMService:
    """Firebase Cloud Messaging wrapper. No-op when FCM is disabled."""

    def __init__(self) -> None:
        self._initialized = False
        self._messaging = None

    def _load_credentials(self):
        import firebase_admin
        from firebase_admin import credentials

        if settings.firebase_credentials_json:
            data = json.loads(settings.firebase_credentials_json)
            return credentials.Certificate(data)
        if settings.firebase_credentials_path:
            return credentials.Certificate(settings.firebase_credentials_path)
        return None

    def _ensure_init(self) -> bool:
        if not settings.fcm_enabled:
            return False
        if self._initialized:
            return self._messaging is not None
        self._initialized = True
        try:
            import firebase_admin
            from firebase_admin import messaging

            if not firebase_admin._apps:
                cred = self._load_credentials()
                options: dict[str, Any] = {"projectId": settings.firebase_project_id}
                if cred:
                    firebase_admin.initialize_app(cred, options)
                else:
                    firebase_admin.initialize_app(options=options)
            self._messaging = messaging
            return True
        except Exception as exc:
            logger.warning("fcm_init_failed", extra={"error": str(exc)})
            return False

    async def send_to_tokens(
        self,
        tokens: list[str],
        *,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
        high_priority: bool = True,
    ) -> None:
        if not tokens or not self._ensure_init():
            logger.info("fcm_skipped", extra={"token_count": len(tokens)})
            return
        assert self._messaging is not None
        message = self._messaging.MulticastMessage(
            tokens=tokens,
            notification=self._messaging.Notification(title=title, body=body),
            data=data or {},
            android=self._messaging.AndroidConfig(
                priority="high" if high_priority else "normal",
            ),
            apns=self._messaging.APNSConfig(
                headers={"apns-priority": "10" if high_priority else "5"},
            ),
        )
        try:
            response = self._messaging.send_each_for_multicast(message)
            logger.info(
                "fcm_sent",
                extra={"success": response.success_count, "failure": response.failure_count},
            )
        except Exception as exc:
            logger.error("fcm_send_failed", extra={"error": str(exc)})
            raise

    async def send_alert(self, tokens: list[str], payload: dict[str, Any]) -> None:
        await self.send_to_tokens(
            tokens,
            title="Emergency Alert",
            body=f"New {payload.get('alert_type', 'SOS')} alert — tap to respond",
            data={k: str(v) for k, v in payload.items()},
            high_priority=True,
        )
