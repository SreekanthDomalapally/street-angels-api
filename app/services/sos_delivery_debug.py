"""SOS delivery diagnostics for debugging push notification failures."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.emergency_types import canonical_code, label_for
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import Alert, AlertRecipient, DeviceToken, Group, GroupInvite, GroupMember, NotificationOutbox, User
from app.repositories.group_repository import GroupRepository
from app.services.routing_service import RoutingService


async def _can_view_delivery(user: User, alert: Alert) -> bool:
    if alert.created_by == user.id:
        return True
    if user.is_admin:
        return True
    return False


async def build_alert_delivery_report(
    db: AsyncSession,
    user: User,
    alert_id: UUID,
) -> dict:
    result = await db.execute(
        select(Alert)
        .where(Alert.id == alert_id)
        .options(selectinload(Alert.recipients).selectinload(AlertRecipient.user))
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError("Alert not found")

    recipient_check = await db.execute(
        select(AlertRecipient.id).where(
            AlertRecipient.alert_id == alert_id,
            AlertRecipient.user_id == user.id,
        )
    )
    if not await _can_view_delivery(user, alert) and recipient_check.scalar_one_or_none() is None:
        raise ForbiddenError("No access to this alert delivery report")

    groups_repo = GroupRepository(db)
    creator = await db.get(User, alert.created_by)
    memberships = await groups_repo.list_memberships_for_user(alert.created_by)
    all_group_ids = [m.group_id for m in memberships]
    type_map = await groups_repo.list_emergency_types_for_groups(all_group_ids)

    alert_code = canonical_code(alert.alert_type)
    matching_groups: list[dict] = []
    for m in memberships:
        configured = type_map.get(m.group_id, [])
        configured_codes = {canonical_code(code) for code in configured}
        matches = not configured or alert_code in configured_codes
        forced = m.group_id == alert.group_id
        if matches or forced:
            group = m.group or await db.get(Group, m.group_id)
            matching_groups.append(
                {
                    "group_id": str(m.group_id),
                    "group_name": group.name if group else None,
                    "emergency_types": configured,
                    "matched_by_type": matches,
                    "forced_primary_group": forced and not matches,
                }
            )

    matching_group_ids = [UUID(g["group_id"]) for g in matching_groups]
    members = await groups_repo.list_members_for_groups(matching_group_ids)
    pending_invites: list[GroupInvite] = []
    for group_id in matching_group_ids:
        pending_invites.extend(await groups_repo.list_pending_invites_for_group(group_id))

    member_rows: list[dict] = []
    for member in members:
        if member.user is None:
            continue
        included = any(
            r.user_id == member.user_id for r in (alert.recipients or [])
        )
        skip_reason: str | None = None
        if member.user_id == alert.created_by:
            skip_reason = "sender"
        elif member.user.suspended:
            skip_reason = "suspended"
        elif not included:
            skip_reason = "not_selected_by_routing"
        member_rows.append(
            {
                "user_id": str(member.user_id),
                "display_name": member.user.full_name,
                "membership_status": "ACTIVE",
                "group_id": str(member.group_id),
                "included_as_recipient": included,
                "skip_reason": skip_reason,
            }
        )

    for invite in pending_invites:
        member_rows.append(
            {
                "user_id": None,
                "display_name": invite.invitee_email or invite.invitee_phone,
                "membership_status": invite.status.upper(),
                "group_id": str(invite.group_id),
                "included_as_recipient": False,
                "skip_reason": f"invite_{invite.status}",
            }
        )

    recipient_ids = [str(r.user_id) for r in alert.recipients or []]
    tokens_result = await db.execute(
        select(DeviceToken).where(DeviceToken.user_id.in_([r.user_id for r in alert.recipients or []]))
    )
    tokens_by_user: dict[str, list[dict]] = {}
    for token in tokens_result.scalars().all():
        key = str(token.user_id)
        tokens_by_user.setdefault(key, []).append(
            {
                "token_preview": f"{token.token[:28]}…" if token.token else None,
                "platform": token.platform,
                "active": True,
            }
        )

    device_tokens = [
        {
            "recipient_user_id": uid,
            "token_exists": uid in tokens_by_user,
            "tokens": tokens_by_user.get(uid, []),
        }
        for uid in recipient_ids
    ]

    recipients_out = [
        {
            "user_id": str(r.user_id),
            "display_name": r.user.full_name if r.user else None,
            "group_id": str(r.group_id) if r.group_id else None,
            "delivery_status": r.delivery_status,
            "delivery_error": r.delivery_error,
            "notified": r.notified,
            "notified_at": r.notified_at.isoformat() if r.notified_at else None,
            "rank": r.rank,
            "score": r.score,
        }
        for r in alert.recipients or []
    ]

    outbox_result = await db.execute(
        select(NotificationOutbox).where(
            NotificationOutbox.payload["alert_id"].astext == str(alert.id)
        )
    )
    outbox_rows = list(outbox_result.scalars().all())
    notification_queue_status = [
        {
            "outbox_id": str(row.id),
            "status": row.status,
            "attempts": row.attempts,
            "last_error": row.last_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "published_at": row.published_at.isoformat() if row.published_at else None,
        }
        for row in outbox_rows
    ]

    skipped_members = [
        m for m in member_rows if not m.get("included_as_recipient")
    ]

    return {
        "alert_id": str(alert.id),
        "sender": {
            "user_id": str(alert.created_by),
            "display_name": creator.full_name if creator else None,
        },
        "emergency_type": {
            "code": alert.alert_type,
            "canonical": alert_code,
            "label": label_for(alert.alert_type),
        },
        "primary_group_id": str(alert.group_id),
        "matching_groups": matching_groups,
        "group_members": member_rows,
        "selected_recipients": recipients_out,
        "skipped_members_with_reasons": skipped_members,
        "recipient_count": len(recipients_out),
        "recipient_user_ids": recipient_ids,
        "device_tokens": device_tokens,
        "recipients_without_tokens": [
            uid for uid in recipient_ids if uid not in tokens_by_user
        ],
        "notification_queue_status": notification_queue_status,
    }


async def build_routing_preview(
    db: AsyncSession,
    user: User,
    *,
    emergency_type: str,
    group_id: UUID,
) -> dict:
    """Preview who would be notified without creating an alert."""
    if not await GroupRepository(db).is_member(group_id, user.id):
        raise ForbiddenError("You are not a member of this group")

    preview_alert = Alert(
        created_by=user.id,
        group_id=group_id,
        alert_type=canonical_code(emergency_type),
        latitude=user.last_known_latitude or 0.0,
        longitude=user.last_known_longitude or 0.0,
        status="active",
    )
    preview_alert.id = UUID(int=0)

    routing = RoutingService(db)
    recipients = await routing.build_recipients(user, preview_alert)

    return {
        "emergency_type": canonical_code(emergency_type),
        "primary_group_id": str(group_id),
        "recipient_count": len(recipients),
        "recipient_user_ids": [str(r.user_id) for r in recipients],
        "recipients": [
            {
                "user_id": str(r.user_id),
                "group_id": str(r.group_id) if r.group_id else None,
                "rank": r.rank,
                "score": r.score,
            }
            for r in recipients
        ],
    }
