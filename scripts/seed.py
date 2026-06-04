"""Seed sample users and a trusted group."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import get_engine
from app.models import Group, GroupMember, User
from sqlalchemy.ext.asyncio import async_sessionmaker


async def seed() -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL required")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for email, name in (
            ("demo@youhooalert.com", "Demo User"),
            ("contact@youhooalert.com", "Trusted Contact"),
        ):
            exists = await session.execute(select(User).where(User.email == email))
            if exists.scalar_one_or_none():
                continue
            session.add(
                User(
                    full_name=name,
                    email=email,
                    password_hash=hash_password("demo12345"),
                    is_verified=True,
                )
            )
        await session.flush()

        demo = (
            await session.execute(select(User).where(User.email == "demo@youhooalert.com"))
        ).scalar_one()
        contact = (
            await session.execute(select(User).where(User.email == "contact@youhooalert.com"))
        ).scalar_one()

        group_exists = await session.execute(
            select(Group).where(Group.name == "Family", Group.created_by == demo.id)
        )
        if not group_exists.scalar_one_or_none():
            group = Group(name="Family", description="Trusted family group", created_by=demo.id)
            session.add(group)
            await session.flush()
            session.add(GroupMember(group_id=group.id, user_id=demo.id, role="owner"))
            session.add(GroupMember(group_id=group.id, user_id=contact.id, role="member"))

        await session.commit()
        print("Seed complete: demo@youhooalert.com / demo12345")


if __name__ == "__main__":
    import asyncio
    import selectors
    import sys

    if sys.platform == "win32":
        asyncio.run(seed(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    else:
        asyncio.run(seed())
