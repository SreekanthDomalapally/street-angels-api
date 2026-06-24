from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Group, GroupEmergencyType, GroupInvite, GroupMember, User
from app.common.group_invite_utils import invite_matches_user
from app.common.emergency_types import normalize_emergency_type_codes


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
            select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group_id)
        )
        return int(result.scalar_one())

    async def member_counts_for_groups(self, group_ids: list[UUID]) -> dict[UUID, int]:
        if not group_ids:
            return {}
        result = await self.db.execute(
            select(GroupMember.group_id, func.count())
            .where(GroupMember.group_id.in_(group_ids))
            .group_by(GroupMember.group_id)
        )
        return {group_id: int(count) for group_id, count in result.all()}

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

    async def get_owned_by_name(self, owner_id: UUID, name: str) -> Group | None:
        normalized = name.strip().lower()
        if not normalized:
            return None
        result = await self.db.execute(
            select(Group).where(
                Group.created_by == owner_id,
                func.lower(Group.name) == normalized,
            )
        )
        return result.scalar_one_or_none()

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

    async def list_members_for_groups(self, group_ids: list[UUID]) -> list[GroupMember]:
        if not group_ids:
            return []
        result = await self.db.execute(
            select(GroupMember)
            .options(selectinload(GroupMember.user))
            .where(GroupMember.group_id.in_(group_ids))
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

    async def get_pending_invite_by_phone(self, group_id: UUID, phone_e164: str) -> GroupInvite | None:
        result = await self.db.execute(
            select(GroupInvite).where(
                GroupInvite.group_id == group_id,
                GroupInvite.invitee_phone == phone_e164,
                GroupInvite.status == "pending",
            )
        )
        return result.scalar_one_or_none()

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

    async def list_pending_invites_for_phone(self, phone_e164: str) -> list[GroupInvite]:
        result = await self.db.execute(
            select(GroupInvite)
            .options(selectinload(GroupInvite.group), selectinload(GroupInvite.inviter))
            .where(
                GroupInvite.invitee_phone == phone_e164,
                GroupInvite.status == "pending",
            )
            .order_by(GroupInvite.created_at.desc())
        )
        return list(result.scalars().all())

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

    async def list_pending_invites_for_recipient(self, user: User) -> list[GroupInvite]:
        """Return pending invites for this user using the same rules as accept/decline."""
        result = await self.db.execute(
            select(GroupInvite)
            .options(selectinload(GroupInvite.group), selectinload(GroupInvite.inviter))
            .where(GroupInvite.status == "pending")
            .order_by(GroupInvite.created_at.desc())
        )
        return [invite for invite in result.scalars().all() if invite_matches_user(invite, user)]

    async def list_emergency_types(self, group_id: UUID) -> list[str]:
        result = await self.db.execute(
            select(GroupEmergencyType.alert_type).where(
                GroupEmergencyType.group_id == group_id
            )
        )
        return normalize_emergency_type_codes(list(result.scalars().all()))

    async def list_emergency_types_for_groups(
        self, group_ids: list[UUID]
    ) -> dict[UUID, list[str]]:
        if not group_ids:
            return {}
        result = await self.db.execute(
            select(GroupEmergencyType.group_id, GroupEmergencyType.alert_type).where(
                GroupEmergencyType.group_id.in_(group_ids)
            )
        )
        mapping: dict[UUID, list[str]] = {}
        for group_id, alert_type in result.all():
            mapping.setdefault(group_id, []).append(alert_type)
        return {
            group_id: normalize_emergency_type_codes(codes)
            for group_id, codes in mapping.items()
        }

    async def set_emergency_types(self, group_id: UUID, codes: list[str]) -> None:
        normalized = normalize_emergency_type_codes(codes)
        await self.db.execute(
            delete(GroupEmergencyType).where(GroupEmergencyType.group_id == group_id)
        )
        for code in normalized:
            self.db.add(GroupEmergencyType(group_id=group_id, alert_type=code))
        await self.db.flush()

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
