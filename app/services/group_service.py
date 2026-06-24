from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GroupMemberRole
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models import AuditLog, Group, GroupInvite, GroupMember, User
from app.common.phone import normalize_phone_e164
from app.repositories.group_repository import GroupRepository
from app.repositories.user_repository import UserRepository
from app.common.group_invite_utils import invite_matches_user
from app.services.group_invite_helpers import (
    ensure_group_invite_for_phone,
    ensure_group_invite_for_user,
)
from app.schemas import (
    GroupCreateRequest,
    GroupDetailResponse,
    GroupInviteListItemResponse,
    GroupInviteRequest,
    GroupListItemResponse,
    GroupMemberAddRequest,
    GroupMemberResponse,
    GroupPendingInviteResponse,
    GroupUpdateRequest,
)


class GroupService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.groups = GroupRepository(db)
        self.users = UserRepository(db)

    async def create(self, user: User, body: GroupCreateRequest) -> Group:
        trimmed = body.name.strip()
        existing = await self.groups.get_owned_by_name(user.id, trimmed)
        if existing:
            raise ValidationError(
                f'You already have a circle named "{existing.name}". Open it to add people.'
            )

        group = Group(
            name=trimmed,
            description=body.description,
            is_temporary=body.is_temporary,
            expires_at=body.expires_at,
            priority=body.priority,
            visibility=body.visibility,
            created_by=user.id,
        )
        await self.groups.create(group)
        await self.groups.add_member(
            GroupMember(group_id=group.id, user_id=user.id, role="owner")
        )
        if body.emergency_types:
            await self.groups.set_emergency_types(
                group.id, [t.value for t in body.emergency_types]
            )
        await self._audit(user.id, "group.create", str(group.id))
        return group

    async def list_for_user(self, user_id: UUID) -> list[GroupListItemResponse]:
        memberships = await self.groups.list_memberships_for_user(user_id)
        group_ids = [m.group.id for m in memberships if m.group is not None]
        types_by_group = await self.groups.list_emergency_types_for_groups(group_ids)
        counts_by_group = await self.groups.member_counts_for_groups(group_ids)
        items: list[GroupListItemResponse] = []
        for membership in memberships:
            group = membership.group
            if group is None:
                continue
            items.append(
                GroupListItemResponse(
                    id=group.id,
                    name=group.name,
                    description=group.description,
                    is_temporary=group.is_temporary,
                    expires_at=group.expires_at,
                    priority=group.priority,
                    visibility=group.visibility,
                    created_by=group.created_by,
                    created_at=group.created_at,
                    member_count=counts_by_group.get(group.id, 0),
                    my_role=membership.role,
                    emergency_types=types_by_group.get(group.id, []),
                )
            )
        return items

    async def get_detail(self, user: User, group_id: UUID) -> GroupDetailResponse:
        if not await self.groups.is_member(group_id, user.id):
            raise ForbiddenError("You are not a member of this group")
        group = await self.groups.get_by_id(group_id)
        if not group:
            raise NotFoundError("Group not found")
        members = [
            GroupMemberResponse(
                user_id=member.user_id,
                full_name=member.user.full_name,
                email=member.user.email,
                role=member.role,
            )
            for member in group.members
            if member.user is not None
        ]
        pending_invites: list[GroupPendingInviteResponse] = []
        membership = next((m for m in group.members if m.user_id == user.id), None)
        if membership and membership.role in ("owner", "admin"):
            invites = await self.groups.list_pending_invites_for_group(group_id)
            pending_invites = [
                GroupPendingInviteResponse(
                    id=invite.id,
                    invitee_email=invite.invitee_email,
                    invitee_phone=invite.invitee_phone,
                    inviter_name=invite.inviter.full_name if invite.inviter else "Someone",
                    status=invite.status,
                    created_at=invite.created_at,
                )
                for invite in invites
            ]
        emergency_types = await self.groups.list_emergency_types(group_id)
        return GroupDetailResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            is_temporary=group.is_temporary,
            expires_at=group.expires_at,
            priority=group.priority,
            visibility=group.visibility,
            created_by=group.created_by,
            created_at=group.created_at,
            member_count=len(members),
            members=members,
            pending_invites=pending_invites,
            emergency_types=emergency_types,
        )

    async def update_group(self, actor: User, group_id: UUID, body: GroupUpdateRequest) -> Group:
        group = await self._require_admin(actor, group_id)
        if body.name is not None:
            trimmed = body.name.strip()
            if trimmed and trimmed.lower() != group.name.lower():
                clash = await self.groups.get_owned_by_name(group.created_by, trimmed)
                if clash and clash.id != group.id:
                    raise ValidationError(f'A circle named "{clash.name}" already exists.')
            group.name = trimmed or group.name
        if body.description is not None:
            group.description = body.description
        if body.priority is not None:
            group.priority = body.priority
        if body.visibility is not None:
            group.visibility = body.visibility
        await self._audit(actor.id, "group.update", str(group_id))
        return group

    async def get_emergency_types(self, user: User, group_id: UUID) -> list[str]:
        if not await self.groups.is_member(group_id, user.id):
            raise ForbiddenError("You are not a member of this group")
        return await self.groups.list_emergency_types(group_id)

    async def set_emergency_types(
        self, actor: User, group_id: UUID, codes: list[str]
    ) -> list[str]:
        await self._require_admin(actor, group_id)
        await self.groups.set_emergency_types(group_id, codes)
        await self._audit(actor.id, "group.emergency_types.update", str(group_id))
        return await self.groups.list_emergency_types(group_id)

    async def add_member(
        self, actor: User, group_id: UUID, body: GroupMemberAddRequest
    ) -> None:
        group = await self._require_admin(actor, group_id)
        member_user = await self.users.get_by_id(body.user_id)
        if not member_user:
            raise NotFoundError("User not found")
        if await self.groups.is_member(group_id, body.user_id):
            raise ForbiddenError("User is already a member")
        if body.role == GroupMemberRole.OWNER:
            raise ValidationError("Cannot assign owner role via API")
        await self.groups.add_member(
            GroupMember(group_id=group.id, user_id=body.user_id, role=body.role.value)
        )
        await self._audit(actor.id, "group.add_member", str(group_id))

    async def remove_member(self, actor: User, group_id: UUID, user_id: UUID) -> None:
        await self._require_admin(actor, group_id)
        if not await self.groups.remove_member(group_id, user_id):
            raise NotFoundError("Member not found")
        await self._audit(actor.id, "group.remove_member", str(group_id))

    async def invite(self, actor: User, group_id: UUID, body: GroupInviteRequest) -> GroupInvite:
        await self._require_admin(actor, group_id)

        if body.user_id:
            invite = await ensure_group_invite_for_user(
                self.db,
                inviter_id=actor.id,
                group_id=group_id,
                target_user_id=body.user_id,
            )
            await self._audit(actor.id, "group.invite", str(group_id))
            return invite

        if body.invitee_phone:
            region = (body.country_code or "IE").upper()
            e164 = normalize_phone_e164(body.invitee_phone, region)
            if not e164:
                raise ValidationError("Enter a valid mobile number")
            existing_user = await self.users.get_by_phone(e164)
            if existing_user:
                invite = await ensure_group_invite_for_user(
                    self.db,
                    inviter_id=actor.id,
                    group_id=group_id,
                    target_user_id=existing_user.id,
                )
            else:
                invite = await ensure_group_invite_for_phone(
                    self.db,
                    inviter_id=actor.id,
                    group_id=group_id,
                    phone_e164=e164,
                )
                if invite is None:
                    raise ValidationError("An invite is already pending for this number")
            await self._audit(actor.id, "group.invite", str(group_id))
            return invite

        if not body.invitee_email:
            raise ValidationError("Provide user_id, invitee_email, or invitee_phone")

        normalized = body.invitee_email.lower()
        existing_user = await self.users.get_by_email(normalized)
        if existing_user:
            if await self.groups.is_member(group_id, existing_user.id):
                raise ValidationError("User is already a member of this group")
            invite = await ensure_group_invite_for_user(
                self.db,
                inviter_id=actor.id,
                group_id=group_id,
                target_user_id=existing_user.id,
            )
            await self._audit(actor.id, "group.invite", str(group_id))
            return invite
        if await self.groups.get_pending_invite(group_id, normalized):
            raise ValidationError("An invite is already pending for this email")
        invite = GroupInvite(
            group_id=group_id,
            inviter_id=actor.id,
            invitee_email=normalized,
        )
        await self.groups.create_invite(invite)
        await self._audit(actor.id, "group.invite", str(group_id))
        return invite

    async def list_my_pending_invites(self, user: User) -> list[GroupInviteListItemResponse]:
        invites = await self.groups.list_pending_invites_for_recipient(user)

        return [
            GroupInviteListItemResponse(
                id=invite.id,
                group_id=invite.group_id,
                group_name=invite.group.name if invite.group else "Trusted circle",
                inviter_name=invite.inviter.full_name if invite.inviter else "Someone",
                invitee_email=invite.invitee_email,
                invitee_phone=invite.invitee_phone,
                status=invite.status,
                created_at=invite.created_at,
            )
            for invite in invites
        ]

    async def accept_invite(self, user: User, invite_id: UUID) -> None:
        invite = await self.groups.get_invite_by_id(invite_id)
        if not invite:
            raise NotFoundError("Invite not found")
        if not invite_matches_user(invite, user):
            raise ForbiddenError("This invite is not for your account")
        if invite.status != "pending":
            raise ValidationError("Invite is no longer pending")
        if not await self.groups.is_member(invite.group_id, user.id):
            await self.groups.add_member(
                GroupMember(group_id=invite.group_id, user_id=user.id, role="member")
            )
        invite.status = "accepted"
        await self._audit(user.id, "group.invite.accept", str(invite.group_id))

    async def decline_invite(self, user: User, invite_id: UUID) -> None:
        invite = await self.groups.get_invite_by_id(invite_id)
        if not invite:
            raise NotFoundError("Invite not found")
        if not invite_matches_user(invite, user):
            raise ForbiddenError("This invite is not for your account")
        if invite.status != "pending":
            raise ValidationError("Invite is no longer pending")
        invite.status = "declined"
        await self._audit(user.id, "group.invite.decline", str(invite.group_id))

    async def _require_admin(self, user: User, group_id: UUID) -> Group:
        group = await self.groups.get_by_id(group_id)
        if not group:
            raise NotFoundError("Group not found")
        member = next((m for m in group.members if m.user_id == user.id), None)
        if not member or member.role not in ("owner", "admin"):
            raise ForbiddenError("Group admin access required")
        return group

    async def _audit(self, user_id: UUID, action: str, resource_id: str) -> None:
        self.db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type="group",
                resource_id=resource_id,
            )
        )
