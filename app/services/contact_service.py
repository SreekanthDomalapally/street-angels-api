from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models import AuditLog, GroupInvite, GroupMember, User
from app.repositories.group_repository import GroupRepository
from app.repositories.user_repository import UserRepository
from app.schemas import ContactDirectoryItem, ContactDirectoryResponse, ContactGroupsUpdateRequest


class ContactService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.groups = GroupRepository(db)
        self.users = UserRepository(db)

    async def directory(self, user: User) -> ContactDirectoryResponse:
        members = await self.groups.list_members_across_user_groups(user.id)
        invites = await self.groups.list_pending_invites_for_admin_groups(user.id)

        by_user: dict[UUID, ContactDirectoryItem] = {}
        for member in members:
            if member.user is None or member.user_id == user.id:
                continue
            entry = by_user.get(member.user_id)
            if entry is None:
                entry = ContactDirectoryItem(
                    user_id=member.user_id,
                    display_name=member.user.full_name,
                    email=member.user.email,
                    phone=member.user.phone_number,
                    group_ids=[],
                    status="member",
                )
                by_user[member.user_id] = entry
            if member.group_id not in entry.group_ids:
                entry.group_ids.append(member.group_id)

        by_email: dict[str, ContactDirectoryItem] = {}
        for invite in invites:
            email = invite.invitee_email.lower()
            matched = await self.users.get_by_email(email)
            if matched:
                continue
            entry = by_email.get(email)
            if entry is None:
                entry = ContactDirectoryItem(
                    user_id=None,
                    display_name=None,
                    email=email,
                    phone=None,
                    group_ids=[],
                    status="invited",
                )
                by_email[email] = entry
            if invite.group_id not in entry.group_ids:
                entry.group_ids.append(invite.group_id)

        contacts = sorted(
            list(by_user.values()) + list(by_email.values()),
            key=lambda item: (item.display_name or item.email or "").lower(),
        )
        return ContactDirectoryResponse(contacts=contacts)

    async def set_member_groups(
        self, actor: User, target_user_id: UUID, body: ContactGroupsUpdateRequest
    ) -> None:
        if target_user_id == actor.id:
            raise ValidationError("Use group settings to manage your own memberships")

        target = await self.users.get_by_id(target_user_id)
        if not target:
            raise NotFoundError("User not found")

        admin_group_ids = set(await self.groups.list_admin_group_ids_for_user(actor.id))
        if not admin_group_ids:
            raise ForbiddenError("You do not manage any groups")

        requested = set(body.group_ids)
        unknown = requested - admin_group_ids
        if unknown:
            raise ForbiddenError("You can only assign contacts to groups you manage")

        for group_id in admin_group_ids:
            member = await self.groups.get_member(group_id, target_user_id)
            should_member = group_id in requested
            if should_member and member is None:
                await self.groups.add_member(
                    GroupMember(group_id=group_id, user_id=target_user_id, role="member")
                )
                await self._audit(actor.id, "contact.add_to_group", str(group_id))
            elif not should_member and member is not None:
                if member.role == "owner":
                    continue
                await self.groups.remove_member(group_id, target_user_id)
                await self._audit(actor.id, "contact.remove_from_group", str(group_id))

    async def assign_invite_groups(
        self, actor: User, email: str, group_ids: list[UUID]
    ) -> None:
        normalized = email.lower().strip()
        admin_group_ids = set(await self.groups.list_admin_group_ids_for_user(actor.id))
        if not admin_group_ids:
            raise ForbiddenError("You do not manage any groups")

        unknown = set(group_ids) - admin_group_ids
        if unknown:
            raise ForbiddenError("You can only invite to groups you manage")

        existing_user = await self.users.get_by_email(normalized)
        for group_id in group_ids:
            if existing_user:
                if not await self.groups.is_member(group_id, existing_user.id):
                    await self.groups.add_member(
                        GroupMember(
                            group_id=group_id,
                            user_id=existing_user.id,
                            role="member",
                        )
                    )
                    await self._audit(actor.id, "contact.add_to_group", str(group_id))
                continue

            if await self.groups.get_pending_invite(group_id, normalized):
                continue

            await self.groups.create_invite(
                GroupInvite(
                    group_id=group_id,
                    inviter_id=actor.id,
                    invitee_email=normalized,
                )
            )
            await self._audit(actor.id, "contact.invite", str(group_id))

    async def _audit(self, user_id: UUID, action: str, resource_id: str) -> None:
        self.db.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type="contact",
                resource_id=resource_id,
            )
        )
