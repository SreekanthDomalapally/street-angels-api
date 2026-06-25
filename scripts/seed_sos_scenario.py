"""
Seed script for the Diya SOS manual test scenario.

Run against staging (not production) after migrations are applied:

    cd C:\\NextSree\\street-angels-api
    set DATABASE_URL=postgresql+asyncpg://...
    python scripts/seed_sos_scenario.py

Expected outcome when Diya sends Personal Safety SOS:
- Sree and Sanjana receive notifications (active group members with device tokens)
- Sushma does NOT (pending invite only)
- Arihanth does NOT (invited, not registered)
- Sreedhar does NOT (not in group)

Verify in Railway logs:
  SOS_TRIGGERED -> ALERT_CREATED -> RECIPIENTS_SELECTED -> NOTIFICATION_QUEUED -> NOTIFICATION_SENT
"""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running as: python scripts/seed_sos_scenario.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db.session import get_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.models import Group, GroupInvite, GroupMember, User


SCENARIO = {
    "group_name": "Diya Circle",
    "owner": "Diya",
    "active_members": ["Sree", "Sanjana"],
    "pending_invite": "Sushma",
    "unregistered_invite_phone": "+15550000001",  # Arihanth placeholder
    "outside_user": "Sreedhar",
}


async def find_user_by_name(session, name: str) -> User | None:
    result = await session.execute(
        select(User).where(User.full_name.ilike(f"%{name}%")).limit(1)
    )
    return result.scalar_one_or_none()


async def main() -> None:
    engine = get_engine()
    if not engine:
        print("DATABASE_URL not configured.")
        sys.exit(1)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        diya = await find_user_by_name(session, SCENARIO["owner"])
        if not diya:
            print(
                "Diya user not found. Create users first, then re-run.\n"
                "Manual setup checklist:\n"
                f"  1. Create group '{SCENARIO['group_name']}' owned by Diya\n"
                f"  2. Add {SCENARIO['active_members']} as accepted members\n"
                f"  3. Invite {SCENARIO['pending_invite']} (pending — not in group_members)\n"
                f"  4. Phone-invite Arihanth (no user account)\n"
                f"  5. Ensure {SCENARIO['outside_user']} is NOT in the group\n"
                "  6. Register Expo push tokens for Sree and Sanjana devices\n"
                "  7. Run: GET /health/notifications on Railway\n"
            )
            sys.exit(0)

        result = await session.execute(
            select(Group).where(Group.created_by == diya.id, Group.name == SCENARIO["group_name"])
        )
        group = result.scalar_one_or_none()
        if not group:
            print(f"Group '{SCENARIO['group_name']}' not found for Diya ({diya.id}).")
            sys.exit(0)

        members = await session.execute(
            select(GroupMember, User)
            .join(User, User.id == GroupMember.user_id)
            .where(GroupMember.group_id == group.id)
        )
        print(f"Group: {group.name} ({group.id})")
        print("Active members:")
        for member, user in members.all():
            print(f"  - {user.full_name} ({user.id})")

        invites = await session.execute(
            select(GroupInvite).where(
                GroupInvite.group_id == group.id,
                GroupInvite.status == "pending",
            )
        )
        pending = list(invites.scalars().all())
        if pending:
            print("Pending invites (should NOT receive SOS):")
            for invite in pending:
                print(f"  - {invite.invitee_email or invite.invitee_phone}")

        print("\nTest: Diya sends Personal Safety SOS")
        print("Expected recipients: Sree, Sanjana only")
        print("Railway log grep: correlation_id alert_id RECIPIENTS_SELECTED NOTIFICATION_SENT")


if __name__ == "__main__":
    asyncio.run(main())
