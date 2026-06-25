"""Alert serialization must not trigger async lazy-load on fresh alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import Alert
from app.services.alert_serializer import serialize_alert


@pytest.mark.asyncio
async def test_serialize_fresh_alert_without_loaded_responses():
    """POST /alerts used to 500 when serialize_alert touched alert.responses lazily."""
    creator_id = uuid4()
    alert_id = uuid4()
    alert = Alert(
        id=alert_id,
        created_by=creator_id,
        group_id=uuid4(),
        alert_type="personal_safety",
        latitude=53.0,
        longitude=-6.0,
        status="active",
        created_at=datetime.now(UTC),
    )

    db = AsyncMock()
    db.get = AsyncMock(
        return_value=MagicMock(
            full_name="Diya",
            phone_number=None,
            phone_verified=False,
        )
    )
    db.scalar = AsyncMock(return_value=2)

    empty_responses = MagicMock()
    empty_responses.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty_responses)

    result = await serialize_alert(db, alert)

    assert str(result.id) == str(alert_id)
    assert result.recipient_count == 2
    assert result.responses == []
    db.execute.assert_awaited()
