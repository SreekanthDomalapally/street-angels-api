from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Group, GroupInvite, GroupMember


class GroupRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, group_id: UUID) -> Group | None:
        result = await self.db.execute(
            select(Group)
            .options(selectinload(Group.members).selectinload(GroupMember.user))
            .where(Group.id == group_id)
        )
        return result.scalar_one_or_none()

    async def member_count(self, group_id: UUID) -> int:
        result = await self.db.execute(
            select(GroupMember.id).where(GroupMember.group_id == group_id)
        )
        return len(result.scalars().all())

    async def list_for_user(self, user_id: UUID) -> list[Group]:
        result = await self.db.execute(
            select(Group)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
            .order_by(Group.created_at.desc())
        )
        return list(result.scalars().unique().all())

    async def list_memberships_for_user(self, user_id: UUID) -> list[GroupMember]:
        result = await self.db.execute(
            select(GroupMember)
            .options(selectinload(GroupMember.group))
            .where(GroupMember.user_id == user_id)
            .order_by(GroupMember.joined_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, group: Group) -> Group:
        self.db.add(group)
        await self.db.flush()
        await self.db.refresh(group)
        return group

    async def add_member(self, member: GroupMember) -> GroupMember:
        self.db.add(member)
        await self.db.flush()
        return member

    async def remove_member(self, group_id: UUID, user_id: UUID) -> bool:
        result = await self.db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.user_id == user_id
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            return False
        await self.db.delete(member)
        return True

    async def is_member(self, group_id: UUID, user_id: UUID) -> bool:
        result = await self.db.execute(
            select(GroupMember.id).where(
                GroupMember.group_id == group_id, GroupMember.user_id == user_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def create_invite(self, invite: GroupInvite) -> GroupInvite:
        self.db.add(invite)
        await self.db.flush()
        await self.db.refresh(invite)
        return invite

    async def get_member(self, group_id: UUID, user_id: UUID) -> GroupMember | None:
        result = await self.db.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_admin_group_ids_for_user(self, user_id: UUID) -> list[UUID]:
        result = await self.db.execute(
            select(GroupMember.group_id).where(
                GroupMember.user_id == user_id,
                GroupMember.role.in_(("owner", "admin")),
            )
        )
        return list(result.scalars().all())

    async def list_members_across_user_groups(self, user_id: UUID) -> list[GroupMember]:
        user_group_ids = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
        result = await self.db.execute(
            select(GroupMember)
            .options(selectinload(GroupMember.user))
            .where(GroupMember.group_id.in_(user_group_ids))
        )
        return list(result.scalars().all())

    async def list_pending_invites_for_admin_groups(self, user_id: UUID) -> list[GroupInvite]:
        admin_group_ids = select(GroupMember.group_id).where(
            GroupMember.user_id == user_id,
            GroupMember.role.in_(("owner", "admin")),
        )
        result = await self.db.execute(
            select(GroupInvite).where(
                GroupInvite.group_id.in_(admin_group_ids),
                GroupInvite.status == "pending",
            )
        )
        return list(result.scalars().all())

    async def get_pending_invite(self, group_id: UUID, email: str) -> GroupInvite | None:
        result = await self.db.execute(
            select(GroupInvite).where(
                GroupInvite.group_id == group_id,
                GroupInvite.invitee_email == email.lower(),
                GroupInvite.status == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def get_invite_by_id(self, invite_id: UUID) -> GroupInvite | None:
        result = await self.db.execute(
            select(GroupInvite)
            .options(selectinload(GroupInvite.group), selectinload(GroupInvite.inviter))
            .where(GroupInvite.id == invite_id)
        )
        return result.scalar_one_or_none()

    async def list_pending_invites_for_email(self, email: str) -> list[GroupInvite]:
        result = await self.db.execute(
            select(GroupInvite)
            .options(selectinload(GroupInvite.group), selectinload(GroupInvite.inviter))
            .where(
                GroupInvite.invitee_email == email.lower(),
                GroupInvite.status == "pending",
            )
            .order_by(GroupInvite.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_pending_invites_for_group(self, group_id: UUID) -> list[GroupInvite]:
        result = await self.db.execute(
            select(GroupInvite)
            .options(selectinload(GroupInvite.inviter))
            .where(
                GroupInvite.group_id == group_id,
                GroupInvite.status == "pending",
            )
            .order_by(GroupInvite.created_at.desc())
        )
        return list(result.scalars().all())
