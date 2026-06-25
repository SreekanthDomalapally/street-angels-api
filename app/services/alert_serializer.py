"""Serialize Alert ORM rows to API responses with creator contact info."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from app.models import Alert, AlertRecipient, AlertResponse, User
from app.schemas import AlertOut, AlertResponseItem


async def _alert_responses(db: AsyncSession, alert: Alert) -> list[AlertResponse]:
    """Load responses without async lazy-load (avoids 500 on POST /alerts)."""
    state = inspect(alert)
    if state.attrs.responses.loaded_value is not attributes.NO_VALUE:
        return list(alert.responses or [])
    result = await db.execute(select(AlertResponse).where(AlertResponse.alert_id == alert.id))
    return list(result.scalars().all())


async def serialize_alert(db: AsyncSession, alert: Alert) -> AlertOut:
    creator = await db.get(User, alert.created_by)
    recipient_count = await db.scalar(
        select(func.count()).select_from(AlertRecipient).where(AlertRecipient.alert_id == alert.id)
    )

    response_items = await _alert_responses(db, alert)
    response_user_ids = {r.user_id for r in response_items}
    responder_users: dict[UUID, User] = {}
    if response_user_ids:
        result = await db.execute(select(User).where(User.id.in_(response_user_ids)))
        responder_users = {u.id: u for u in result.scalars().all()}

    out = AlertOut.model_validate(alert)
    out.creator_name = creator.full_name if creator else None
    if creator and creator.phone_number and creator.phone_verified:
        out.creator_phone = creator.phone_number
    else:
        out.creator_phone = None
    out.recipient_count = int(recipient_count or 0)

    enriched_responses: list[AlertResponseItem] = []
    for item in response_items:
        resp = AlertResponseItem.model_validate(item)
        user = responder_users.get(item.user_id)
        if user:
            resp.responder_name = user.full_name
            if user.phone_verified and user.phone_number:
                resp.responder_phone = user.phone_number
        enriched_responses.append(resp)
    out.responses = enriched_responses
    return out


async def serialize_alerts(db: AsyncSession, alerts: list[Alert]) -> list[AlertOut]:
    if not alerts:
        return []

    alert_ids = [alert.id for alert in alerts]
    creator_ids = list({alert.created_by for alert in alerts})

    creators_result = await db.execute(select(User).where(User.id.in_(creator_ids)))
    creators = {user.id: user for user in creators_result.scalars().all()}

    counts_result = await db.execute(
        select(AlertRecipient.alert_id, func.count())
        .where(AlertRecipient.alert_id.in_(alert_ids))
        .group_by(AlertRecipient.alert_id)
    )
    recipient_counts = {alert_id: int(count) for alert_id, count in counts_result.all()}

    responses_result = await db.execute(
        select(AlertResponse).where(AlertResponse.alert_id.in_(alert_ids))
    )
    responses_by_alert: dict[UUID, list[AlertResponse]] = {}
    for response in responses_result.scalars().all():
        responses_by_alert.setdefault(response.alert_id, []).append(response)

    response_user_ids = {
        response.user_id for responses in responses_by_alert.values() for response in responses
    }
    responder_users: dict[UUID, User] = {}
    if response_user_ids:
        responders_result = await db.execute(select(User).where(User.id.in_(response_user_ids)))
        responder_users = {user.id: user for user in responders_result.scalars().all()}

    serialized: list[AlertOut] = []
    for alert in alerts:
        out = AlertOut.model_validate(alert)
        creator = creators.get(alert.created_by)
        out.creator_name = creator.full_name if creator else None
        if creator and creator.phone_number and creator.phone_verified:
            out.creator_phone = creator.phone_number
        else:
            out.creator_phone = None
        out.recipient_count = recipient_counts.get(alert.id, 0)

        enriched_responses: list[AlertResponseItem] = []
        for item in responses_by_alert.get(alert.id, []):
            resp = AlertResponseItem.model_validate(item)
            user = responder_users.get(item.user_id)
            if user:
                resp.responder_name = user.full_name
                if user.phone_verified and user.phone_number:
                    resp.responder_phone = user.phone_number
            enriched_responses.append(resp)
        out.responses = enriched_responses
        serialized.append(out)

    return serialized
