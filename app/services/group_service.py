from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import GroupMemberRole
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models import AuditLog, Group, GroupInvite, GroupMember, User
from app.repositories.group_repository import GroupRepository
from app.repositories.user_repository import UserRepository
from app.schemas import GroupCreateRequest, GroupInviteRequest, GroupMemberAddRequest


class GroupService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.groups = GroupRepository(db)
        self.users = UserRepository(db)

    async def create(self, user: User, body: GroupCreateRequest) -> Group:
        group = Group(
            name=body.name.strip(),
            description=body.description,
            is_temporary=body.is_temporary,
            expires_at=body.expires_at,
            created_by=user.id,
        )
        await self.groups.create(group)
        await self.groups.add_member(
            GroupMember(group_id=group.id, user_id=user.id, role="owner")
        )
        await self._audit(user.id, "group.create", str(group.id))
        return group

    async def list_for_user(self, user_id: UUID) -> list[Group]:
        return await self.groups.list_for_user(user_id)

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
        invite = GroupInvite(
            group_id=group_id,
            inviter_id=actor.id,
            invitee_email=body.invitee_email.lower(),
        )
        await self.groups.create_invite(invite)
        await self._audit(actor.id, "group.invite", str(group_id))
        return invite

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
