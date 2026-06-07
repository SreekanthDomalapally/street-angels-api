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
