import asyncio
import json
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_token
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)

WS_FANOUT_CHANNEL = "ws:alert_fanout"


class AlertWebSocketManager:
    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._redis: redis.Redis | None = None
        self._pubsub_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._pubsub_task is not None:
            return
        self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        self._pubsub_task = asyncio.create_task(self._listen_fanout())

    async def stop(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
            self._pubsub_task = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def _listen_fanout(self) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(WS_FANOUT_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                    alert_id = envelope["alert_id"]
                    payload = envelope["message"]
                    await self._local_broadcast(alert_id, payload)
                except Exception:
                    continue
        finally:
            await pubsub.unsubscribe(WS_FANOUT_CHANNEL)
            await pubsub.close()

    async def connect(self, alert_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._channels.setdefault(alert_id, set()).add(websocket)
        logger.info("ws_connected", extra={"alert_id": alert_id})

    async def disconnect(self, alert_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if alert_id in self._channels:
                self._channels[alert_id].discard(websocket)
                if not self._channels[alert_id]:
                    del self._channels[alert_id]

    async def broadcast(self, alert_id: str, message: dict[str, Any]) -> None:
        await self._local_broadcast(alert_id, message)
        try:
            if self._redis is None:
                self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.publish(
                WS_FANOUT_CHANNEL,
                json.dumps({"alert_id": alert_id, "message": message}),
            )
        except Exception as exc:
            logger.warning("ws_fanout_publish_failed", extra={"error": str(exc)})

    async def _local_broadcast(self, alert_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._channels.get(alert_id, set()))
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(alert_id, ws)

    @staticmethod
    def authenticate(token: str | None) -> str | None:
        if not token:
            return None
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                return None
            return payload["sub"]
        except Exception:
            return None


alert_ws_manager = AlertWebSocketManager()


async def websocket_endpoint(
    websocket: WebSocket,
    alert_id: str,
    token: str | None,
    db: AsyncSession,
) -> None:
    user_id_str = AlertWebSocketManager.authenticate(token)
    if not user_id_str:
        await websocket.close(code=4401)
        return

    try:
        user_id = UUID(user_id_str)
        alert_uuid = UUID(alert_id)
    except ValueError:
        await websocket.close(code=4400)
        return

    user = await UserRepository(db).get_by_id(user_id)
    if not user or user.suspended:
        await websocket.close(code=4401)
        return

    from app.services.alert_service import AlertService

    try:
        await AlertService(db).require_alert_access(user, alert_uuid)
    except Exception:
        await websocket.close(code=4403)
        return

    await alert_ws_manager.connect(alert_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await alert_ws_manager.disconnect(alert_id, websocket)
