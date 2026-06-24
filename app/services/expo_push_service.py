"""Push delivery via Expo's push service.

The mobile app registers Expo push tokens (``ExponentPushToken[...]``). Expo
relays each message to FCM (Android) and APNs (iOS), so the backend never talks
to Firebase/APNs directly. Requires the FCM v1 service-account key to be
uploaded to the Expo project credentials (not to this service).
"""

from __future__ import annotations

from typing import Any, Iterable

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_EXPO_TOKEN_PREFIXES = ("ExponentPushToken[", "ExpoPushToken[")
_MAX_TOKENS_PER_MESSAGE = 100


def _chunk(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class ExpoPushService:
    @staticmethod
    def _is_expo_token(token: str) -> bool:
        return token.startswith(_EXPO_TOKEN_PREFIXES)

    async def send_to_tokens(
        self,
        tokens: list[str],
        *,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        channel_id: str | None = None,
        high_priority: bool = True,
    ) -> list[str]:
        """Send a notification. Returns tokens that are no longer registered."""
        valid = [t for t in dict.fromkeys(tokens) if t and self._is_expo_token(t)]
        if not settings.push_enabled or not valid:
            logger.info(
                "push_skipped",
                extra={"valid": len(valid), "received": len(tokens)},
            )
            return []

        messages = [
            {
                "to": chunk,
                "title": title,
                "body": body,
                "data": data or {},
                "sound": "default",
                "priority": "high" if high_priority else "default",
                **({"channelId": channel_id} if channel_id else {}),
            }
            for chunk in _chunk(valid, _MAX_TOKENS_PER_MESSAGE)
        ]

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if settings.expo_access_token:
            headers["Authorization"] = f"Bearer {settings.expo_access_token}"

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(EXPO_PUSH_URL, json=messages, headers=headers)
                if resp.status_code >= 400:
                    # Expo returns a JSON error body explaining bad requests/credentials.
                    body = resp.text[:500]
                    logger.error(
                        "push_send_http_error",
                        extra={"status": resp.status_code, "body": body},
                    )
                    raise RuntimeError(f"Expo push HTTP {resp.status_code}: {body}")
                return self._collect_stale(resp.json(), valid)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("push_send_failed", extra={"error": repr(exc)})
            raise RuntimeError(f"Expo push request failed: {exc!r}") from exc

    def _collect_stale(self, payload: dict[str, Any], tokens: list[str]) -> list[str]:
        """Tickets come back in token order; pair them up to find dead tokens.

        Delivery accounting must never raise: Expo already accepted the push by the
        time we parse tickets, so a logging/parsing error here must not abort the
        worker or dead-letter an emergency that was actually delivered.
        """
        tickets = payload.get("data", []) if isinstance(payload, dict) else []
        ok = 0
        stale: list[str] = []
        for token, ticket in zip(tokens, tickets):
            if not isinstance(ticket, dict):
                continue
            if ticket.get("status") == "ok":
                ok += 1
                continue
            err = (ticket.get("details") or {}).get("error")
            # NOTE: "message" is a reserved LogRecord attribute — never put it in `extra`.
            try:
                logger.warning(
                    "push_ticket_error",
                    extra={"ticket_message": ticket.get("message"), "error": err},
                )
            except Exception:  # pragma: no cover - logging must never break delivery
                pass
            if err == "DeviceNotRegistered":
                stale.append(token)
        try:
            logger.info(
                "push_sent",
                extra={"tokens": len(tokens), "ok": ok, "errors": len(tickets) - ok},
            )
        except Exception:  # pragma: no cover - logging must never break delivery
            pass
        return stale

    async def send_alert(self, tokens: list[str], payload: dict[str, Any]) -> list[str]:
        from app.common.emergency_types import label_for

        type_label = label_for(str(payload.get("alert_type", "")))
        sender = payload.get("sender_name")
        title = f"{sender} needs help" if sender else "Emergency alert"
        return await self.send_to_tokens(
            tokens,
            title=title,
            body=f"{type_label} — tap to respond",
            data={
                "type": "sos_alert",
                "alert_id": str(payload.get("alert_id", "")),
                "alert_type": str(payload.get("alert_type", "")),
                "sender_name": str(payload.get("sender_name") or ""),
            },
            channel_id="emergency",
            high_priority=True,
        )
