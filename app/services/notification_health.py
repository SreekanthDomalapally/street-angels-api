"""Notification pipeline diagnostics for /health/notifications."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select, text

from app.core.config import settings
from app.db.session import get_engine
from app.models import Alert, AlertRecipient, DeviceToken, User
from app.workers.notification_worker import notification_worker


def _redis_host_is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in {"", "localhost", "127.0.0.1", "::1"}


def _build_issues(report: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    redis = report["checks"]["redis"]
    if not redis["ok"]:
        issues.append(
            {
                "severity": "critical",
                "code": "redis_unreachable",
                "message": (
                    "Redis is not reachable. SOS alerts save to the database but push "
                    "notifications are silently skipped."
                ),
                "fix": "On Railway: add a Redis service and set REDIS_URL=${{ Redis.REDIS_URL }}, then redeploy.",
            }
        )

    if redis.get("localhost_default"):
        issues.append(
            {
                "severity": "critical",
                "code": "redis_localhost",
                "message": "REDIS_URL points to localhost — invalid inside Railway containers.",
                "fix": "Set REDIS_URL=${{ Redis.REDIS_URL }} on the API service and redeploy.",
            }
        )

    worker = report["checks"]["worker"]
    if not worker["running"] or not worker["task_alive"]:
        issues.append(
            {
                "severity": "critical",
                "code": "worker_not_running",
                "message": "The in-process notification worker is not running.",
                "fix": "Restart the API service and check deploy logs for notification_worker_started.",
            }
        )

    push = report["checks"]["push"]
    if not push["enabled"]:
        issues.append(
            {
                "severity": "critical",
                "code": "push_disabled",
                "message": "PUSH_ENABLED is false — no push notifications will be sent.",
                "fix": "Set PUSH_ENABLED=true on the API service.",
            }
        )

    if redis["ok"] and redis.get("dlq", 0) > 0:
        issues.append(
            {
                "severity": "warning",
                "code": "dlq_not_empty",
                "message": f"{redis['dlq']} failed notification(s) in the dead-letter queue.",
                "fix": "Check Railway logs for notification_process_failed and push_send_failed.",
            }
        )

    tokens = report["checks"]["device_tokens"]
    if tokens.get("users_without_tokens", 0) > 0:
        issues.append(
            {
                "severity": "warning",
                "code": "users_missing_push_tokens",
                "message": (
                    f"{tokens['users_without_tokens']} user(s) have no registered push token — "
                    "they cannot receive SOS pushes."
                ),
                "fix": (
                    "Each recipient must open the Play/App Store build (not Expo Go), grant "
                    "notifications, and complete onboarding."
                ),
            }
        )

    alerts = report["checks"]["recent_alerts"]
    if alerts.get("last_24h_with_zero_recipients", 0) > 0:
        issues.append(
            {
                "severity": "warning",
                "code": "alerts_without_recipients",
                "message": (
                    f"{alerts['last_24h_with_zero_recipients']} SOS in the last 24h had zero "
                    "routed recipients (solo group or routing gap)."
                ),
                "fix": "Ensure the SOS group has other members and emergency types are configured.",
            }
        )

    if not report["checks"]["firebase_auth"]["credentials_configured"]:
        issues.append(
            {
                "severity": "info",
                "code": "firebase_auth_not_configured",
                "message": "Firebase credentials not set (phone/Google login may fail).",
                "fix": "Set FIREBASE_CREDENTIALS_JSON — not required for push (Expo handles delivery).",
            }
        )

    return issues


def _overall_status(issues: list[dict[str, str]]) -> str:
    severities = {issue["severity"] for issue in issues}
    if "critical" in severities:
        return "error"
    if "warning" in severities:
        return "degraded"
    return "ok"


async def _device_token_stats() -> dict[str, Any]:
    engine = get_engine()
    if engine is None:
        return {
            "available": False,
            "total_device_tokens": None,
            "users_with_tokens": None,
            "total_users": None,
            "users_without_tokens": None,
        }

    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        total_tokens = await session.scalar(select(func.count()).select_from(DeviceToken)) or 0
        users_with = await session.scalar(
            select(func.count(func.distinct(DeviceToken.user_id))).select_from(DeviceToken)
        ) or 0
        total_users = await session.scalar(select(func.count()).select_from(User)) or 0

    return {
        "available": True,
        "total_device_tokens": int(total_tokens),
        "users_with_tokens": int(users_with),
        "total_users": int(total_users),
        "users_without_tokens": int(total_users) - int(users_with),
    }


async def _recent_alert_stats() -> dict[str, Any]:
    engine = get_engine()
    if engine is None:
        return {"available": False}

    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        last_24h = await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.created_at >= func.now() - text("interval '24 hours'"))
        ) or 0

        zero_recipient_alerts = await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.created_at >= func.now() - text("interval '24 hours'"),
                ~Alert.id.in_(select(AlertRecipient.alert_id).distinct()),
            )
        ) or 0

    return {
        "available": True,
        "last_24h": int(last_24h),
        "last_24h_with_zero_recipients": int(zero_recipient_alerts),
        "last_24h_with_recipients": int(last_24h) - int(zero_recipient_alerts),
    }


async def collect_notification_health() -> dict[str, Any]:
    """Build a full notification-pipeline diagnostic report."""
    redis = await notification_worker.queue.health_check()
    redis["localhost_default"] = _redis_host_is_local(settings.redis_url)

    worker = notification_worker.status_snapshot()

    push = {
        "enabled": settings.push_enabled,
        "provider": "expo",
        "expo_access_token_set": bool(settings.expo_access_token),
    }

    firebase_auth = {
        "credentials_configured": bool(
            settings.firebase_credentials_json or settings.firebase_credentials_path
        ),
        "project_id": settings.firebase_project_id,
        "note": "Used for phone/Google login only — SOS push uses Expo, not Firebase Admin.",
    }

    device_tokens = await _device_token_stats()
    recent_alerts = await _recent_alert_stats()

    report: dict[str, Any] = {
        "status": "ok",
        "environment": settings.environment,
        "checks": {
            "redis": redis,
            "worker": worker,
            "push": push,
            "firebase_auth": firebase_auth,
            "device_tokens": device_tokens,
            "recent_alerts": recent_alerts,
        },
        "issues": [],
    }

    report["issues"] = _build_issues(report)
    report["status"] = _overall_status(report["issues"])
    report["push_pipeline"] = (
        "SOS → PostgreSQL → Redis queue → notification worker → Expo Push API → FCM/APNs → device"
    )

    return report
