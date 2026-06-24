"""Serialize Alert ORM rows to API responses with creator contact info."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, AlertRecipient, User
from app.schemas import AlertOut, AlertResponseItem


async def serialize_alert(db: AsyncSession, alert: Alert) -> AlertOut:
    creator = await db.get(User, alert.created_by)
    recipient_count = await db.scalar(
        select(func.count()).select_from(AlertRecipient).where(AlertRecipient.alert_id == alert.id)
    )

    response_user_ids = {r.user_id for r in alert.responses}
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
    for item in alert.responses:
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

    response_user_ids = {
        response.user_id for alert in alerts for response in alert.responses
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
        for item in alert.responses:
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
