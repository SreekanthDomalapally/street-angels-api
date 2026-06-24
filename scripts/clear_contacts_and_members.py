"""Clear trusted contacts, non-owner group members, and pending invites."""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select

from app.db.session import get_engine
from app.models import GroupInvite, GroupMember, PhoneInvite, TrustedContact, User
from sqlalchemy.ext.asyncio import async_sessionmaker


async def clear_contacts_and_members() -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL required")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        users = (await session.execute(select(User.id, User.full_name, User.phone_number))).all()
        print(f"Users ({len(users)}):")
        for user_id, name, phone in users:
            print(f"  - {name} ({phone or 'no phone'}) [{user_id}]")

        trusted_before = await session.scalar(select(func.count()).select_from(TrustedContact))
        members_before = await session.scalar(select(func.count()).select_from(GroupMember))
        group_invites_before = await session.scalar(select(func.count()).select_from(GroupInvite))
        phone_invites_before = await session.scalar(select(func.count()).select_from(PhoneInvite))

        await session.execute(delete(TrustedContact))
        await session.execute(delete(GroupMember).where(GroupMember.role != "owner"))
        await session.execute(delete(GroupInvite))
        await session.execute(delete(PhoneInvite))
        await session.commit()

        trusted_after = await session.scalar(select(func.count()).select_from(TrustedContact))
        members_after = await session.scalar(select(func.count()).select_from(GroupMember))
        group_invites_after = await session.scalar(select(func.count()).select_from(GroupInvite))
        phone_invites_after = await session.scalar(select(func.count()).select_from(PhoneInvite))

        owners = (
            await session.execute(
                select(GroupMember.group_id, User.full_name)
                .join(User, User.id == GroupMember.user_id)
                .where(GroupMember.role == "owner")
            )
        ).all()

        print()
        print("Cleared:")
        print(f"  trusted_contacts: {trusted_before} -> {trusted_after}")
        print(f"  group_members:    {members_before} -> {members_after} (owners kept)")
        print(f"  group_invites:    {group_invites_before} -> {group_invites_after}")
        print(f"  phone_invites:    {phone_invites_before} -> {phone_invites_after}")
        print()
        print("Group owners remaining:")
        for group_id, name in owners:
            print(f"  - {name} owns group {group_id}")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(
            clear_contacts_and_members(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(clear_contacts_and_members())
