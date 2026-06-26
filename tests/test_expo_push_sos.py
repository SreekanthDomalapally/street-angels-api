"""Expo SOS push payload shape tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.common.push_constants import SOS_ALERT_CHANNEL_ID
from app.services.expo_push_service import ExpoPushService


@pytest.mark.asyncio
async def test_send_alert_builds_whatsapp_style_payload():
    svc = ExpoPushService()
    captured: list[dict] = []

    async def fake_post(_url, json=None, headers=None):
        captured.extend(json or [])
        class Response:
            status_code = 200

            def json(self):
                return {"data": [{"status": "ok", "id": "ticket-abc"}]}

        return Response()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = fake_post
        stale = await svc.send_alert(
            ["ExponentPushToken[sample-token]"],
            {
                "alert_id": "alert-123",
                "alert_type": "personal_safety",
                "sender_name": "Diya",
                "sender_user_id": "user-diya",
                "correlation_id": "corr-1",
            },
        )

    assert len(captured) == 1
    msg = captured[0]
    assert msg["to"] == "ExponentPushToken[sample-token]"
    assert msg["title"] == "Diya needs help"
    assert "Safety" in msg["body"]
    assert "live location" in msg["body"]
    assert msg["channelId"] == SOS_ALERT_CHANNEL_ID == "sos-alerts"
    assert msg["data"]["type"] == "SOS_ALERT"
    assert msg["data"]["alertId"] == "alert-123"
    assert msg["data"]["senderUserId"] == "user-diya"
    assert stale == []
