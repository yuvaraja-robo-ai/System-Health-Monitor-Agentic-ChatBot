import asyncio
import logging

from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.hub import hub

router = APIRouter(tags=["ws"])
log = logging.getLogger(__name__)


async def _send_json(ws: WebSocket, payload: object) -> None:
    await ws.send_json(jsonable_encoder(payload))


async def _stream(ws: WebSocket, topic: str) -> None:
    await ws.accept()
    q = hub.subscribe(topic)
    try:
        latest = hub.latest(topic)
        if latest is not None:
            await _send_json(ws, latest)
        while True:
            env = await q.get()
            await _send_json(ws, env)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws %s failed", topic)
    finally:
        hub.unsubscribe(topic, q)


@router.websocket("/ws/system")
async def ws_system(ws: WebSocket) -> None:
    await _stream(ws, "system")


@router.websocket("/ws/processes")
async def ws_processes(ws: WebSocket) -> None:
    await _stream(ws, "processes")


@router.websocket("/ws/logs")
async def ws_logs(ws: WebSocket) -> None:
    await _stream(ws, "logs")


@router.websocket("/ws/leaks")
async def ws_leaks(ws: WebSocket) -> None:
    await _stream(ws, "leaks")


@router.websocket("/ws/health")
async def ws_health(ws: WebSocket) -> None:
    await _stream(ws, "health")


@router.websocket("/ws/jetson")
async def ws_jetson(ws: WebSocket) -> None:
    await _stream(ws, "jetson")
