"""Inspect group invites vs user accounts."""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.db.session import get_engine
from app.models import GroupInvite, User
from app.common.group_invite_utils import invite_matches_user
from sqlalchemy.ext.asyncio import async_sessionmaker


async def inspect() -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL required")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        invites = (
            await session.execute(
                select(GroupInvite).where(GroupInvite.status == "pending").order_by(GroupInvite.created_at.desc())
            )
        ).scalars().all()

        print(f"Users: {len(users)}")
        for user in users:
            print(
                f"  {user.full_name} | email={user.email!r} | phone={user.phone_number!r} | verified={user.phone_verified}"
            )

        print(f"\nPending group invites: {len(invites)}")
        for invite in invites:
            print(
                f"  group={invite.group_id} | email={invite.invitee_email!r} | phone={invite.invitee_phone!r}"
            )
            for user in users:
                if invite_matches_user(invite, user):
                    print(f"    -> matches {user.full_name}")

        print("\nSimulated GET /groups/invites/mine:")
        for user in users:
            seen: set = set()
            matched = []
            if user.email:
                for invite in invites:
                    if invite.invitee_email.lower() == user.email.lower() and invite.id not in seen:
                        seen.add(invite.id)
                        matched.append(invite)
            if user.phone_number:
                for invite in invites:
                    if invite.invitee_phone == user.phone_number and invite.id not in seen:
                        seen.add(invite.id)
                        matched.append(invite)
            print(f"  {user.full_name}: {len(matched)} invite(s) via current API logic")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(
            inspect(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(inspect())
