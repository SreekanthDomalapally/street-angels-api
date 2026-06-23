from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.phone import normalize_phone_e164
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models import GroupInvite, GroupMember
from app.repositories.group_repository import GroupRepository, phone_placeholder_email
from app.repositories.user_repository import UserRepository


async def ensure_group_invite_for_phone(
    db: AsyncSession,
    *,
    inviter_id: UUID,
    group_id: UUID,
    phone_e164: str,
) -> GroupInvite | None:
    groups = GroupRepository(db)
    users = UserRepository(db)

    existing_user = await users.get_by_phone(phone_e164)
    if existing_user and await groups.is_member(group_id, existing_user.id):
        return None

    pending = await groups.get_pending_invite_by_phone(group_id, phone_e164)
    if pending:
        return pending

    invite = GroupInvite(
        group_id=group_id,
        inviter_id=inviter_id,
        invitee_email=phone_placeholder_email(phone_e164),
        invitee_phone=phone_e164,
        status="pending",
    )
    return await groups.create_invite(invite)


async def ensure_group_invite_for_user(
    db: AsyncSession,
    *,
    inviter_id: UUID,
    group_id: UUID,
    target_user_id: UUID,
) -> GroupInvite:
    groups = GroupRepository(db)
    users = UserRepository(db)

    target = await users.get_by_id(target_user_id)
    if not target:
        raise NotFoundError("User not found")
    if await groups.is_member(group_id, target_user_id):
        raise ValidationError("User is already a member of this group")

    if target.phone_verified and target.phone_number:
        pending = await groups.get_pending_invite_by_phone(group_id, target.phone_number)
        if pending:
            return pending
        invite = GroupInvite(
            group_id=group_id,
            inviter_id=inviter_id,
            invitee_email=target.email.lower() if target.email else phone_placeholder_email(target.phone_number),
            invitee_phone=target.phone_number,
            status="pending",
        )
        return await groups.create_invite(invite)

    if not target.email:
        raise ValidationError("User has no email or verified phone for group invite")

    normalized = target.email.lower()
    pending = await groups.get_pending_invite(group_id, normalized)
    if pending:
        return pending
    invite = GroupInvite(
        group_id=group_id,
        inviter_id=inviter_id,
        invitee_email=normalized,
        status="pending",
    )
    return await groups.create_invite(invite)


def invite_matches_user(invite: GroupInvite, user) -> bool:
    if invite.status != "pending":
        return False
    if user.phone_number and invite.invitee_phone and invite.invitee_phone == user.phone_number:
        return True
    if user.email and invite.invitee_email.lower() == user.email.lower():
        if invite.invitee_email.endswith("@phone.pending"):
            return False
        return True
    if user.phone_number and invite.invitee_email == phone_placeholder_email(user.phone_number):
        return True
    return False
