"""Tests for notification pipeline diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.notification_health import collect_notification_health


@pytest.mark.asyncio
async def test_collect_notification_health_ok_when_all_green():
    with (
        patch(
            "app.services.notification_health.notification_worker.queue.health_check",
            new_callable=AsyncMock,
            return_value={
                "ok": True,
                "host": "redis.railway.internal",
                "latency_ms": 1.5,
                "queue_pending": 0,
                "dlq": 0,
                "error": None,
            },
        ),
        patch(
            "app.services.notification_health._device_token_stats",
            new_callable=AsyncMock,
            return_value={
                "available": True,
                "total_device_tokens": 5,
                "users_with_tokens": 5,
                "total_users": 5,
                "users_without_tokens": 0,
            },
        ),
        patch(
            "app.services.notification_health._recent_alert_stats",
            new_callable=AsyncMock,
            return_value={
                "available": True,
                "last_24h": 2,
                "last_24h_with_zero_recipients": 0,
                "last_24h_with_recipients": 2,
            },
        ),
        patch(
            "app.services.notification_health.notification_worker.status_snapshot",
            return_value={"running": True, "task_alive": True},
        ),
        patch("app.services.notification_health.settings.push_enabled", True),
        patch(
            "app.services.notification_health.settings.redis_url",
            "redis://redis.railway.internal:6379",
        ),
        patch(
            "app.services.notification_health.settings.firebase_credentials_json",
            '{"type":"service_account"}',
        ),
    ):
        report = await collect_notification_health()

    assert report["status"] == "ok"
    assert report["issues"] == []
    assert report["checks"]["redis"]["ok"] is True
    assert report["checks"]["worker"]["task_alive"] is True


@pytest.mark.asyncio
async def test_collect_notification_health_error_when_redis_down():
    with (
        patch(
            "app.services.notification_health.notification_worker.queue.health_check",
            new_callable=AsyncMock,
            return_value={
                "ok": False,
                "host": "localhost",
                "latency_ms": None,
                "queue_pending": None,
                "dlq": None,
                "error": "Connection refused",
            },
        ),
        patch(
            "app.services.notification_health._device_token_stats",
            new_callable=AsyncMock,
            return_value={"available": False},
        ),
        patch(
            "app.services.notification_health._recent_alert_stats",
            new_callable=AsyncMock,
            return_value={"available": False},
        ),
        patch(
            "app.services.notification_health.notification_worker.status_snapshot",
            return_value={"running": True, "task_alive": True},
        ),
        patch("app.services.notification_health.settings.push_enabled", True),
        patch(
            "app.services.notification_health.settings.redis_url",
            "redis://localhost:6379/0",
        ),
        patch(
            "app.services.notification_health.settings.firebase_credentials_json",
            None,
        ),
        patch("app.services.notification_health.settings.firebase_credentials_path", None),
    ):
        report = await collect_notification_health()

    assert report["status"] == "error"
    codes = {issue["code"] for issue in report["issues"]}
    assert "redis_unreachable" in codes
    assert "redis_localhost" in codes


@pytest.mark.asyncio
async def test_health_notifications_endpoint_returns_503_on_error():
    from app.main import app

    error_report = {
        "status": "error",
        "environment": "production",
        "checks": {},
        "issues": [{"severity": "critical", "code": "redis_unreachable", "message": "x", "fix": "y"}],
        "push_pipeline": "test",
    }

    with patch(
        "app.services.notification_health.collect_notification_health",
        new_callable=AsyncMock,
        return_value=error_report,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/notifications")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["issues"][0]["code"] == "redis_unreachable"


@pytest.mark.asyncio
async def test_health_notifications_endpoint_returns_200_when_ok():
    from app.main import app

    ok_report = {
        "status": "ok",
        "environment": "production",
        "checks": {"redis": {"ok": True}},
        "issues": [],
        "push_pipeline": "test",
    }

    with patch(
        "app.services.notification_health.collect_notification_health",
        new_callable=AsyncMock,
        return_value=ok_report,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/notifications")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
