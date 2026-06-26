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
            medical_background="Asthma",
            blood_group="O+",
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


@pytest.mark.asyncio
async def test_medical_info_visible_to_recipients_only():
    creator_id = uuid4()
    recipient_id = uuid4()
    alert = Alert(
        id=uuid4(),
        created_by=creator_id,
        group_id=uuid4(),
        alert_type="medical",
        latitude=53.0,
        longitude=-6.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    creator = MagicMock(
        full_name="Alex",
        phone_number="+353871234567",
        phone_verified=True,
        medical_background="Diabetes",
        blood_group="A+",
    )
    recipient = MagicMock(id=recipient_id)

    db = AsyncMock()
    db.get = AsyncMock(return_value=creator)
    db.scalar = AsyncMock(return_value=1)
    empty_responses = MagicMock()
    empty_responses.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty_responses)

    for_viewer = await serialize_alert(db, alert, viewer=recipient)
    assert for_viewer.creator_blood_group == "A+"
    assert for_viewer.creator_medical_background == "Diabetes"

    for_creator = await serialize_alert(db, alert, viewer=MagicMock(id=creator_id))
    assert for_creator.creator_blood_group is None
    assert for_creator.creator_medical_background is None
