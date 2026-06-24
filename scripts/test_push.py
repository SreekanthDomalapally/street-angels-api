"""End-to-end push test: send a real Expo push to registered device tokens and
print the raw per-device ticket result.

This bypasses the alert pipeline and talks to Expo directly, so it isolates
whether push *delivery* works (Expo + FCM/APNs credentials + token validity).

Usage:
    python scripts/test_push.py                 # send to ALL registered tokens
    python scripts/test_push.py --phone +3538...  # only that user's tokens
    python scripts/test_push.py --dry-run         # list tokens, send nothing

Run it where the database + internet are reachable (e.g. Railway shell).
Reads DATABASE_URL / EXPO_ACCESS_TOKEN from the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import selectors
import sys

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import get_engine
from app.models import DeviceToken, User

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_PREFIXES = ("ExponentPushToken[", "ExpoPushToken[")


async def run(*, phone: str | None, dry_run: bool) -> None:
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        stmt = select(DeviceToken, User).join(User, DeviceToken.user_id == User.id)
        if phone:
            stmt = stmt.where(User.phone_number == phone)
        rows = (await db.execute(stmt)).all()

    if not rows:
        print("No device tokens found" + (f" for {phone}" if phone else "") + ".")
        return

    print(f"Found {len(rows)} device token(s):")
    valid: list[str] = []
    for token_row, user in rows:
        is_expo = token_row.token.startswith(EXPO_PREFIXES)
        marker = "ok" if is_expo else "NON-EXPO (will be skipped)"
        label = getattr(user, "full_name", None) or getattr(user, "phone_number", None) or str(user.id)
        print(f"  - {label:<24} {token_row.platform:<8} {token_row.token[:32]}...  [{marker}]")
        if is_expo:
            valid.append(token_row.token)

    if dry_run:
        print("\nDry run. Re-run without --dry-run to send a test push.")
        return

    if not valid:
        print("\nNo valid Expo tokens to send to.")
        return

    messages = [
        {
            "to": valid,
            "title": "Street Angels test",
            "body": "Push pipeline test — if you see this, delivery works.",
            "sound": "default",
            "priority": "high",
            "channelId": "emergency",
            "data": {"type": "test"},
        }
    ]
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    access = os.environ.get("EXPO_ACCESS_TOKEN")
    if access:
        headers["Authorization"] = f"Bearer {access}"

    print(f"\nSending to {len(valid)} token(s) via Expo...")
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(EXPO_PUSH_URL, json=messages, headers=headers)

    print(f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        print(resp.text[:1000])
        return

    tickets = data.get("data", []) if isinstance(data, dict) else []
    if not tickets:
        print(f"Unexpected response: {data}")
        return

    ok = 0
    for token, ticket in zip(valid, tickets):
        status = ticket.get("status")
        if status == "ok":
            ok += 1
            print(f"  ok    {token[:32]}...  id={ticket.get('id')}")
        else:
            err = (ticket.get("details") or {}).get("error")
            print(f"  ERROR {token[:32]}...  {status}: {err} — {ticket.get('message')}")

    print(f"\n{ok}/{len(tickets)} accepted by Expo.")
    print(
        "If you see ok above but no notification arrives, the token is on Expo Go "
        "or the build lacks FCM v1 credentials (run `eas credentials`)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a test Expo push.")
    parser.add_argument("--phone", help="Only send to this user's tokens (E.164, e.g. +35385...)")
    parser.add_argument("--dry-run", action="store_true", help="List tokens, send nothing")
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.run(
            run(phone=args.phone, dry_run=args.dry_run),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(run(phone=args.phone, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
