"""Standalone notification worker entrypoint for Railway worker service."""

from __future__ import annotations

import asyncio
import selectors
import sys

from app.workers.notification_worker import notification_worker


async def main() -> None:
    await notification_worker.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await notification_worker.stop()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
    else:
        asyncio.run(main())
