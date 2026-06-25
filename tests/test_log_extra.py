"""Tests for logging helpers and push ticket parsing."""

from __future__ import annotations

import logging

from app.core.log_extra import safe_extra
from app.services.expo_push_service import ExpoPushService


def test_safe_extra_strips_reserved_message_key():
    extra = safe_extra(message="must not leak", alert_id="abc", error="x")
    assert "message" not in extra
    assert extra["alert_id"] == "abc"
    assert extra["error"] == "x"


def test_safe_extra_allows_logging_without_keyerror():
    logger = logging.getLogger("test.safe_extra")
    logger.info("push_ticket_error", extra=safe_extra(ticket_message="device error", error="x"))


def test_collect_stale_tolerates_ticket_message_field():
    service = ExpoPushService()
    payload = {
        "data": [
            {"status": "error", "message": "InvalidCredentials", "details": {"error": "x"}},
            {"status": "ok"},
        ]
    }
    tokens = ["ExponentPushToken[a]", "ExponentPushToken[b]"]
    stale = service._collect_stale(payload, tokens)
    assert stale == []
