from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.phone import normalize_phone_e164
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models import AuditLog, GroupInvite, GroupMember, User
from app.repositories.group_repository import GroupRepository
from app.repositories.user_repository import UserRepository
from app.schemas import ContactDirectoryItem, ContactDirectoryResponse, ContactGroupsUpdateRequest
from app.services.group_invite_helpers import ensure_group_invite_for_user


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
        by_phone: dict[str, ContactDirectoryItem] = {}
        for invite in invites:
            if invite.invitee_phone:
                phone = invite.invitee_phone
                matched = await self.users.get_by_phone(phone)
                if matched:
                    if await self.groups.is_member(invite.group_id, matched.id):
                        continue
                    entry = by_user.get(matched.id)
                    if entry is None:
                        entry = ContactDirectoryItem(
                            user_id=matched.id,
                            display_name=matched.full_name,
                            email=matched.email,
                            phone=matched.phone_number,
                            group_ids=[],
                            status="invited",
                        )
                        by_user[matched.id] = entry
                    elif entry.status != "member":
                        entry.status = "invited"
                    if invite.group_id not in entry.group_ids:
                        entry.group_ids.append(invite.group_id)
                    continue
                entry = by_phone.get(phone)
                if entry is None:
                    entry = ContactDirectoryItem(
                        user_id=None,
                        display_name=None,
                        email=None,
                        phone=phone,
                        group_ids=[],
                        status="invited",
                    )
                    by_phone[phone] = entry
                if invite.group_id not in entry.group_ids:
                    entry.group_ids.append(invite.group_id)
                continue

            email = invite.invitee_email.lower()
            if email.endswith("@phone.pending"):
                continue
            matched = await self.users.get_by_email(email)
            if matched:
                if await self.groups.is_member(invite.group_id, matched.id):
                    continue
                entry = by_user.get(matched.id)
                if entry is None:
                    entry = ContactDirectoryItem(
                        user_id=matched.id,
                        display_name=matched.full_name,
                        email=matched.email,
                        phone=matched.phone_number,
                        group_ids=[],
                        status="invited",
                    )
                    by_user[matched.id] = entry
                elif entry.status != "member":
                    entry.status = "invited"
                if invite.group_id not in entry.group_ids:
                    entry.group_ids.append(invite.group_id)
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
            list(by_user.values()) + list(by_email.values()) + list(by_phone.values()),
            key=lambda item: (item.display_name or item.email or item.phone or "").lower(),
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

        target_email = (target.email or "").lower()
        for group_id in admin_group_ids:
            member = await self.groups.get_member(group_id, target_user_id)
            should_member = group_id in requested
            if should_member and member is None:
                if target_email and await self.groups.get_pending_invite(group_id, target_email):
                    continue
                if target.phone_verified and target.phone_number:
                    if await self.groups.get_pending_invite_by_phone(group_id, target.phone_number):
                        continue
                await ensure_group_invite_for_user(
                    self.db,
                    inviter_id=actor.id,
                    group_id=group_id,
                    target_user_id=target_user_id,
                )
                await self._audit(actor.id, "contact.invite", str(group_id))
            elif not should_member and member is not None:
                if member.role == "owner":
                    continue
                await self.groups.remove_member(group_id, target_user_id)
                await self._audit(actor.id, "contact.remove_from_group", str(group_id))

    async def assign_invite_groups(
        self, actor: User, group_ids: list[UUID], email: str | None = None, phone_number: str | None = None, country_code: str | None = None
    ) -> None:
        admin_group_ids = set(await self.groups.list_admin_group_ids_for_user(actor.id))
        if not admin_group_ids:
            raise ForbiddenError("You do not manage any groups")

        unknown = set(group_ids) - admin_group_ids
        if unknown:
            raise ForbiddenError("You can only invite to groups you manage")

        if phone_number:
            region = (country_code or "IE").upper()
            e164 = normalize_phone_e164(phone_number, region)
            if not e164:
                raise ValidationError("Enter a valid mobile number")
            existing_user = await self.users.get_by_phone(e164)
            for group_id in group_ids:
                if existing_user and await self.groups.is_member(group_id, existing_user.id):
                    continue
                if existing_user:
                    await ensure_group_invite_for_user(
                        self.db,
                        inviter_id=actor.id,
                        group_id=group_id,
                        target_user_id=existing_user.id,
                    )
                else:
                    from app.services.group_invite_helpers import ensure_group_invite_for_phone

                    await ensure_group_invite_for_phone(
                        self.db,
                        inviter_id=actor.id,
                        group_id=group_id,
                        phone_e164=e164,
                    )
                await self._audit(actor.id, "contact.invite", str(group_id))
            return

        if not email:
            raise ValidationError("Provide email or phone_number")

        normalized = email.lower().strip()
        existing_user = await self.users.get_by_email(normalized)
        for group_id in group_ids:
            if existing_user and await self.groups.is_member(group_id, existing_user.id):
                continue
            if existing_user:
                await ensure_group_invite_for_user(
                    self.db,
                    inviter_id=actor.id,
                    group_id=group_id,
                    target_user_id=existing_user.id,
                )
            elif await self.groups.get_pending_invite(group_id, normalized):
                continue
            else:
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
