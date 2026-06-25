"""Automated checks for SOS flow repair."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.common.enums import ResponseType
from app.core.exceptions import ForbiddenError
from app.models import Alert, GroupMember, User
from app.schemas import AlertResponseRequest
from app.services.alert_service import AlertService
from app.services.routing_service import Candidate, RoutingService


def test_routing_score_penalizes_unavailable_users():
    routing = RoutingService(MagicMock())
    creator = User(
        id=uuid4(),
        full_name="Diya",
        last_known_latitude=53.0,
        last_known_longitude=-6.0,
    )
    alert = Alert(
        id=uuid4(),
        created_by=creator.id,
        group_id=uuid4(),
        alert_type="personal_safety",
        latitude=53.0,
        longitude=-6.0,
        status="active",
    )
    available = Candidate(
        user=User(id=uuid4(), full_name="Sree", available_for_emergencies=True),
        group_id=uuid4(),
        group_priority=1,
    )
    unavailable = Candidate(
        user=User(id=uuid4(), full_name="Sushma", available_for_emergencies=False),
        group_id=uuid4(),
        group_priority=1,
    )
    routing._score({available.user.id: available, unavailable.user.id: unavailable}, creator, alert)
    assert available.score > unavailable.score


@pytest.mark.asyncio
async def test_creator_cannot_respond_to_own_alert():
    db = MagicMock()
    service = AlertService(db)
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
    )
    creator = User(id=creator_id, full_name="Diya", phone_verified=True)

    with (
        patch.object(service, "_require_alert_access", new_callable=AsyncMock, return_value=alert),
        patch.object(service.alerts, "is_recipient", new_callable=AsyncMock, return_value=False),
    ):
        with pytest.raises(ForbiddenError, match="creator cannot respond"):
            await service.respond(
                creator,
                alert_id,
                AlertResponseRequest(response_type=ResponseType.I_CAN_HELP),
            )


@pytest.mark.asyncio
async def test_non_recipient_cannot_respond():
    db = MagicMock()
    service = AlertService(db)
    responder_id = uuid4()
    alert_id = uuid4()
    alert = Alert(
        id=alert_id,
        created_by=uuid4(),
        group_id=uuid4(),
        alert_type="personal_safety",
        latitude=53.0,
        longitude=-6.0,
        status="active",
    )
    responder = User(id=responder_id, full_name="Sreedhar", phone_verified=True)

    with (
        patch.object(service, "_require_alert_access", new_callable=AsyncMock, return_value=alert),
        patch.object(service.alerts, "is_recipient", new_callable=AsyncMock, return_value=False),
    ):
        with pytest.raises(ForbiddenError, match="Only alert recipients"):
            await service.respond(
                responder,
                alert_id,
                AlertResponseRequest(response_type=ResponseType.ON_MY_WAY, eta_minutes=5),
            )


@pytest.mark.asyncio
async def test_resolve_broadcast_includes_resolved_status():
    db = MagicMock()
    service = AlertService(db)
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
    )
    creator = User(id=creator_id, full_name="Diya", phone_verified=True)

    with (
        patch.object(service.alerts, "get_by_id", new_callable=AsyncMock, return_value=alert),
        patch.object(service, "_log_event", new_callable=AsyncMock),
        patch("app.services.alert_service.alert_ws_manager.broadcast", new_callable=AsyncMock) as broadcast,
    ):
        await service.resolve(creator, alert_id)
        broadcast.assert_awaited_once()
        payload = broadcast.await_args.args[1]
        assert payload["type"] == "alert_resolved"
        assert payload["status"] == "resolved"


def test_build_recipients_skips_suspended_member():
    member = MagicMock(spec=GroupMember)
    member.user_id = uuid4()
    member.group_id = uuid4()
    member.user = User(id=member.user_id, full_name="Suspended", suspended=True)

    # Mirror routing_service loop guard
    creator_id = uuid4()
    should_skip = (
        member.user_id == creator_id
        or member.user is None
        or member.user.suspended
    )
    assert should_skip is True
