"""Remove duplicate owned groups with the same name (keeps richest / oldest)."""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select

from app.db.session import get_engine
from app.models import Group, GroupInvite, GroupMember, PhoneInvite, User
from sqlalchemy.ext.asyncio import async_sessionmaker


def normalize_name(name: str) -> str:
    return name.strip().lower()


async def dedupe_owned_groups(*, owner_phone: str | None = None, dry_run: bool = True) -> None:
    engine = get_engine()
    if engine is None:
        raise RuntimeError("DATABASE_URL required")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        if owner_phone:
            owners = [u for u in users if u.phone_number == owner_phone]
            if not owners:
                raise RuntimeError(f"No user with phone {owner_phone}")
        else:
            owners = users

        print(f"Scanning {len(owners)} user(s) for duplicate owned group names…")
        to_delete: list[Group] = []

        for owner in owners:
            groups = (
                await session.execute(
                    select(Group).where(Group.created_by == owner.id).order_by(Group.created_at.asc())
                )
            ).scalars().all()

            by_name: dict[str, list[Group]] = {}
            for group in groups:
                by_name.setdefault(normalize_name(group.name), []).append(group)

            for name_key, bucket in by_name.items():
                if len(bucket) < 2:
                    continue

                scores: list[tuple[Group, int, float]] = []
                for group in bucket:
                    member_count = await session.scalar(
                        select(func.count())
                        .select_from(GroupMember)
                        .where(GroupMember.group_id == group.id)
                    )
                    pending = await session.scalar(
                        select(func.count())
                        .select_from(GroupInvite)
                        .where(GroupInvite.group_id == group.id, GroupInvite.status == "pending")
                    )
                    scores.append(
                        (
                            group,
                            (member_count or 0) + (pending or 0),
                            group.created_at.timestamp(),
                        )
                    )
                scores.sort(key=lambda item: (item[1], item[2]), reverse=True)
                keep = scores[0][0]
                duplicates = [item[0] for item in scores[1:]]

                print()
                print(f"{owner.full_name} — duplicate name {name_key!r}:")
                print(f"  KEEP   {keep.name} [{keep.id}]")
                for dup in duplicates:
                    print(f"  DELETE {dup.name} [{dup.id}]")
                    to_delete.append(dup)

        if not to_delete:
            print("\nNo duplicate owned groups found.")
            return

        if dry_run:
            print(f"\nDry run only — would delete {len(to_delete)} group(s). Re-run with --apply.")
            return

        ids = [group.id for group in to_delete]
        await session.execute(delete(GroupInvite).where(GroupInvite.group_id.in_(ids)))
        await session.execute(delete(PhoneInvite).where(PhoneInvite.group_id.in_(ids)))
        await session.execute(delete(GroupMember).where(GroupMember.group_id.in_(ids)))
        await session.execute(delete(Group).where(Group.id.in_(ids)))
        await session.commit()
        print(f"\nDeleted {len(to_delete)} duplicate group(s).")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    phone = "+919618934571"
    for arg in sys.argv[1:]:
        if arg.startswith("+") or arg.isdigit():
            phone = arg if arg.startswith("+") else f"+{arg}"

    if sys.platform == "win32":
        asyncio.run(
            dedupe_owned_groups(owner_phone=phone, dry_run=not apply),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(dedupe_owned_groups(owner_phone=phone, dry_run=not apply))
