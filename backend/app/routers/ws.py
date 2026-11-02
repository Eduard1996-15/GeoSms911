"""Canal WebSocket para el dashboard en tiempo real."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..events import bus
from ..security import decode_access_token

router = APIRouter(tags=["tiempo real"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")) -> None:
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    queue = bus.subscribe()
    try:
        await websocket.send_json(
            {"type": "hello", "data": {"user_id": user_id, "subscribers": bus.subscriber_count}}
        )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "data": {}})
                continue

            owner = (event.get("data") or {}).get("user_id")
            if owner is not None and owner != user_id:
                continue
            await websocket.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(queue)
