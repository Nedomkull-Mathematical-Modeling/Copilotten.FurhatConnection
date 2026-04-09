"""
Copilotten Furhat Bridge
========================
FastAPI WebSocket server that bridges:
  - A browser/frontend (microphone audio via WebSocket)
  - OpenAI Realtime API (speech-to-text + LLM response)
  - Furhat robot (text-to-speech via WebSocket)

Flow:
  1. Frontend sends config (Furhat IP + OpenAI API key)
  2. Server opens WebSocket connections to both Furhat and OpenAI
  3. Microphone audio (PCM16 @ 24 kHz) is streamed to OpenAI
  4. On response.done, the assistant text is sent to the Furhat robot
     via request.speak.text so the robot reads it aloud

Run with:
    uvicorn main:app --reload
"""

import asyncio
import base64
import json
import logging

import websockets
import websockets.exceptions
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Copilotten Furhat Bridge")

app.mount("/static", StaticFiles(directory="static"), name="static")

OPENAI_REALTIME_URI = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"

SYSTEM_INSTRUCTIONS = (
    "You are Copilotten, a friendly and helpful AI assistant embodied in a Furhat robot. "
    "Keep your responses concise and conversational."
)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(client_ws: WebSocket) -> None:
    await client_ws.accept()
    logger.info("Frontend client connected")
    try:
        config = await client_ws.receive_json()
        if config.get("type") != "config":
            await client_ws.send_json(
                {"type": "error", "message": "First message must be a config object"}
            )
            return

        furhat_ip: str = config.get("furhat_ip", "").strip()
        openai_api_key: str = config.get("openai_api_key", "").strip()

        if not furhat_ip:
            await client_ws.send_json(
                {"type": "error", "message": "furhat_ip is required"}
            )
            return
        if not openai_api_key:
            await client_ws.send_json(
                {"type": "error", "message": "openai_api_key is required"}
            )
            return

        await run_bridge(client_ws, furhat_ip, openai_api_key)

    except WebSocketDisconnect:
        logger.info("Client disconnected before session started")
    except Exception:
        logger.exception("Unexpected error in websocket_endpoint")
        try:
            await client_ws.send_json(
                {"type": "error", "message": "Internal server error"}
            )
        except Exception:
            pass


async def run_bridge(
    client_ws: WebSocket,
    furhat_ip: str,
    openai_api_key: str,
) -> None:
    """Open connections to Furhat and OpenAI, then bridge messages between all three."""

    furhat_uri = f"ws://{furhat_ip}:9000/v1/events"
    openai_headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    await client_ws.send_json(
        {"type": "status", "message": f"Connecting to Furhat at {furhat_ip}…"}
    )

    try:
        async with websockets.connect(furhat_uri, open_timeout=10) as furhat_ws:
            await client_ws.send_json(
                {
                    "type": "status",
                    "message": "Connected to Furhat. Connecting to OpenAI…",
                }
            )

            async with websockets.connect(
                OPENAI_REALTIME_URI,
                additional_headers=openai_headers,
                open_timeout=15,
            ) as openai_ws:
                await client_ws.send_json(
                    {
                        "type": "status",
                        "message": "Connected to OpenAI. Configuring session…",
                    }
                )

                # Configure the Realtime session: audio in, text out, server VAD
                await openai_ws.send(
                    json.dumps(
                        {
                            "type": "session.update",
                            "session": {
                                "modalities": ["text"],
                                "instructions": SYSTEM_INSTRUCTIONS,
                                "input_audio_format": "pcm16",
                                "input_audio_transcription": {"model": "whisper-1"},
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.5,
                                    "prefix_padding_ms": 300,
                                    "silence_duration_ms": 700,
                                },
                            },
                        }
                    )
                )

                await client_ws.send_json({"type": "connected"})
                logger.info("Bridge session started (Furhat: %s)", furhat_ip)

                stop = asyncio.Event()

                async def handle_openai_messages() -> None:
                    try:
                        async for raw in openai_ws:
                            event = json.loads(raw)
                            etype = event.get("type", "")
                            logger.debug("OpenAI → %s", etype)

                            if etype == "input_audio_buffer.speech_started":
                                await client_ws.send_json({"type": "vad_speech_started"})

                            elif etype == "input_audio_buffer.speech_stopped":
                                await client_ws.send_json({"type": "vad_speech_stopped"})

                            elif etype == "conversation.item.input_audio_transcription.completed":
                                transcript = event.get("transcript", "")
                                if transcript:
                                    await client_ws.send_json(
                                        {
                                            "type": "transcript",
                                            "role": "user",
                                            "text": transcript,
                                        }
                                    )

                            elif etype == "response.text.delta":
                                await client_ws.send_json(
                                    {
                                        "type": "transcript_delta",
                                        "role": "assistant",
                                        "delta": event.get("delta", ""),
                                    }
                                )

                            elif etype == "response.done":
                                text = _extract_text(event.get("response", {}))
                                if text:
                                    await client_ws.send_json(
                                        {
                                            "type": "transcript",
                                            "role": "assistant",
                                            "text": text,
                                        }
                                    )
                                    await furhat_ws.send(
                                        json.dumps(
                                            {
                                                "event_name": "request.speak.text",
                                                "text": text,
                                                "abort": True,
                                            }
                                        )
                                    )
                                    logger.info("Sent to Furhat: %.80s", text)

                            elif etype == "error":
                                err = event.get("error", {})
                                await client_ws.send_json(
                                    {
                                        "type": "error",
                                        "message": err.get("message", "Unknown OpenAI error"),
                                    }
                                )
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    finally:
                        stop.set()

                async def handle_furhat_messages() -> None:
                    try:
                        async for raw in furhat_ws:
                            event = json.loads(raw)
                            ename = event.get("event_name", "")
                            logger.debug("Furhat → %s", ename)
                            await client_ws.send_json(
                                {"type": "furhat_event", "event": event}
                            )
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    finally:
                        stop.set()

                async def handle_client_messages() -> None:
                    try:
                        while not stop.is_set():
                            try:
                                msg = await client_ws.receive()
                            except WebSocketDisconnect:
                                break

                            if msg.get("type") == "websocket.disconnect":
                                break

                            raw_bytes = msg.get("bytes")
                            raw_text = msg.get("text")

                            if raw_bytes:
                                # PCM16 audio chunk – forward to OpenAI
                                audio_b64 = base64.b64encode(raw_bytes).decode()
                                await openai_ws.send(
                                    json.dumps(
                                        {
                                            "type": "input_audio_buffer.append",
                                            "audio": audio_b64,
                                        }
                                    )
                                )
                            elif raw_text:
                                data = json.loads(raw_text)
                                if data.get("type") == "commit_audio":
                                    # Manual commit for push-to-talk mode
                                    await openai_ws.send(
                                        json.dumps({"type": "input_audio_buffer.commit"})
                                    )
                                    await openai_ws.send(
                                        json.dumps({"type": "response.create"})
                                    )
                    except WebSocketDisconnect:
                        pass
                    finally:
                        stop.set()

                tasks = [
                    asyncio.create_task(handle_openai_messages()),
                    asyncio.create_task(handle_furhat_messages()),
                    asyncio.create_task(handle_client_messages()),
                ]
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc and not isinstance(
                        exc,
                        (WebSocketDisconnect, websockets.exceptions.ConnectionClosed),
                    ):
                        logger.error("Task error: %s", exc, exc_info=exc)

    except (OSError, websockets.exceptions.WebSocketException) as exc:
        logger.error("Connection error: %s", exc)
        try:
            await client_ws.send_json(
                {"type": "error", "message": f"Connection failed: {exc}"}
            )
        except Exception:
            pass
    except Exception:
        logger.exception("Bridge error")
        try:
            await client_ws.send_json(
                {"type": "error", "message": "Unexpected bridge error"}
            )
        except Exception:
            pass


def _extract_text(response: dict) -> str:
    """Extract assistant text from an OpenAI response.done payload."""
    parts: list[str] = []
    for item in response.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif part.get("type") == "audio":
                    transcript = part.get("transcript", "")
                    if transcript:
                        parts.append(transcript)
    return " ".join(p for p in parts if p)
