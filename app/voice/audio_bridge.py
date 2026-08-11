"""WebSocket Audio Bridge for streaming voice frames between UI & Voice Pipeline."""

import logging
import json
import base64
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
from nicegui import app

from app.voice.pipeline import PipecatVoicePipeline

logger = logging.getLogger("talenthunt.voice.bridge")


class AudioBridgeConnectionManager:
    """Manages active voice WebSocket client connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket voice client connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket voice client disconnected.")


manager = AudioBridgeConnectionManager()


@app.websocket("/ws/audio")
async def audio_websocket_endpoint(websocket: WebSocket):
    """FastAPI WebSocket endpoint for bi-directional real-time audio streaming."""
    from app.infrastructure.auth import SESSION_COOKIE, is_authenticated

    if not is_authenticated(websocket.cookies.get(SESSION_COOKIE)):
        await websocket.close(code=4401, reason="Authentication required")
        return
    await manager.connect(websocket)
    pipeline = PipecatVoicePipeline()

    try:
        while True:
            data = await websocket.receive_text()

            try:
                payload = json.loads(data)
                if not isinstance(payload, dict):
                    continue
                msg_type = payload.get("type")

                if msg_type == "audio_chunk":
                    raw_b64 = payload.get("data", "")
                    if raw_b64:
                        frame_bytes = base64.b64decode(raw_b64)
                        pipeline.append_audio_frame(frame_bytes)

                elif msg_type in ("stop_recording", "process_audio"):
                    async def _process_and_send():
                        async for event in pipeline.process_voice_input():
                            try:
                                await websocket.send_json(event)
                            except (WebSocketDisconnect, RuntimeError, Exception):
                                break
                    asyncio.create_task(_process_and_send())

                elif msg_type == "clear_buffer":
                    pipeline.clear_buffer()
                    await websocket.send_json({"type": "status", "state": "idle", "message": "Buffer cleared"})

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

            except json.JSONDecodeError:
                logger.warning("Received invalid JSON on audio WebSocket endpoint.")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error(f"Error in WebSocket voice stream: {exc}")
        manager.disconnect(websocket)


def setup_audio_bridge(fastapi_app=app) -> None:
    """Helper function to register audio bridge routes if needed."""
    logger.info("Audio WebSocket bridge endpoint initialized at /ws/audio.")
