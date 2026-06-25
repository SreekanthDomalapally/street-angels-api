"""Inspect, requeue, or clear the notification dead-letter queue (DLQ).

Usage:
    python scripts/recover_dlq.py                # show DLQ contents
    python scripts/recover_dlq.py --requeue      # move DLQ entries back to the queue
    python scripts/recover_dlq.py --clear        # delete DLQ entries

Where to run:
    **Recommended:** Railway dashboard → API service → Shell (REDIS_URL is set automatically).

    From your PC only if .env has the Railway **public** REDIS_URL (not redis.railway.internal).
    localhost:6379 will not reach production — the script exits with instructions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from pathlib import Path

import redis.asyncio as redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings

QUEUE_KEY = "notifications:queue"
DLQ_KEY = "notifications:dlq"


def _resolve_redis_url() -> str:
    return settings.redis_url.strip() or "redis://localhost:6379/0"


def _is_local_redis(url: str) -> bool:
    lowered = url.lower()
    return (
        "localhost" in lowered
        or "127.0.0.1" in lowered
        or lowered.startswith("redis://:@localhost")
    )


def _print_local_redis_help() -> None:
    print(
        "\nERROR: REDIS_URL points to localhost - this cannot clear production DLQ.\n"
        "\nDo this instead (takes ~30 seconds):\n"
        "  1. Open https://railway.app -> your project\n"
        "  2. Click the API service (street-angels-api)\n"
        "  3. Open the Shell tab\n"
        "  4. Run:  python scripts/recover_dlq.py --clear\n"
        "\nOptional from your PC: copy the Redis public URL from Railway -> Redis service\n"
        "-> Variables -> REDIS_URL into api/.env, then re-run this script.\n"
        "(Internal host redis.railway.internal only works inside Railway.)\n"
    )


async def run(*, requeue: bool, clear: bool) -> None:
    url = _resolve_redis_url()
    if _is_local_redis(url):
        _print_local_redis_help()
        raise SystemExit(1)

    client = redis.from_url(url, decode_responses=True)

    try:
        depth = int(await client.llen(DLQ_KEY))
        print(f"DLQ depth: {depth}  (redis: {url.split('@')[-1]})")

        entries = await client.lrange(DLQ_KEY, 0, 49)
        for i, raw in enumerate(entries):
            try:
                entry = json.loads(raw)
                print(
                    f"  [{i}] type={entry.get('type')} "
                    f"alert={entry.get('alert_id')} "
                    f"recipients={len(entry.get('recipient_user_ids', []))} "
                    f"error={str(entry.get('error'))[:200]}"
                )
            except (ValueError, TypeError):
                print(f"  [{i}] unparseable: {raw[:200]}")

        if requeue:
            moved = 0
            while True:
                item = await client.lpop(DLQ_KEY)
                if item is None:
                    break
                try:
                    payload = json.loads(item)
                    payload.pop("error", None)
                    await client.rpush(QUEUE_KEY, json.dumps(payload))
                    moved += 1
                except (ValueError, TypeError):
                    continue
            print(f"\nRequeued {moved} notification(s) for retry.")
        elif clear:
            removed = int(await client.llen(DLQ_KEY))
            await client.delete(DLQ_KEY)
            print(f"\nCleared {removed} DLQ entry(ies).")
        else:
            print("\nDry run. Use --requeue to retry or --clear to delete.")
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Recover the notification DLQ.")
    parser.add_argument("--requeue", action="store_true", help="Move DLQ entries back to the queue")
    parser.add_argument("--clear", action="store_true", help="Delete all DLQ entries")
    args = parser.parse_args()

    if args.requeue and args.clear:
        parser.error("Choose either --requeue or --clear, not both.")

    if sys.platform == "win32":
        asyncio.run(
            run(requeue=args.requeue, clear=args.clear),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(run(requeue=args.requeue, clear=args.clear))


if __name__ == "__main__":
    main()
