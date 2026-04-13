"""
Furhat Bridge
=============
FastAPI WebSocket server that bridges:
  - A browser/frontend (monitor UI via WebSocket)
  - OpenAI Realtime API (speech-to-text + LLM + TTS via WebSocket)
  - Furhat robot (microphone input + audio output via furhat-realtime-api)

Flow:
  1. Frontend sends config (Furhat IP + OpenAI API key)
  2. Server connects to Furhat via AsyncFurhatClient and to OpenAI via WebSocket
  3. On session.created, the session is configured and OpenAI generates a greeting
  4. Furhat microphone audio (PCM16 @ 24 kHz) is streamed to OpenAI
  5. OpenAI audio deltas are streamed back to Furhat for real-time playback
  6. When Furhat finishes speaking the robot resumes listening
  7. Transcripts are forwarded to the browser UI

Run with:
    furhat-bridge
  or:
    uvicorn furhat_bridge.server:app --reload
"""

import asyncio
import json
import logging
from pathlib import Path

import websockets
import websockets.exceptions
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from furhat_realtime_api import AsyncFurhatClient, Events

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Furhat Bridge")

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

OPENAI_REALTIME_URI = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview"

SYSTEM_INSTRUCTIONS = (
    "You are Copilotten, a friendly and helpful AI assistant embodied in a Furhat robot. "
    "Keep your responses concise and conversational."
)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / "index.html"))


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
    """Connect to Furhat via furhat-realtime-api and OpenAI via WebSocket, then bridge."""

    openai_headers = {
        "Authorization": f"Bearer {openai_api_key}",
        "OpenAI-Beta": "realtime=v1",
    }

    await client_ws.send_json(
        {"type": "status", "message": f"Connecting to Furhat at {furhat_ip}…"}
    )

    furhat = AsyncFurhatClient(furhat_ip)
    try:
        await furhat.connect()
    except Exception as exc:
        logger.error("Failed to connect to Furhat: %s", exc)
        try:
            await client_ws.send_json(
                {"type": "error", "message": f"Could not connect to Furhat: {exc}"}
            )
        except Exception:
            pass
        return

    try:
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
                    "message": "Connected to OpenAI. Starting session…",
                }
            )

            stop = asyncio.Event()
            output_started = False

            # ── Furhat event handlers ─────────────────────────────────────

            async def on_furhat_audio(data: dict) -> None:
                """Forward Furhat microphone audio to OpenAI."""
                audio = data.get("microphone")
                if audio:
                    try:
                        await openai_ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": audio,
                                }
                            )
                        )
                    except websockets.exceptions.ConnectionClosed:
                        pass

            async def on_furhat_speak_end(data: dict) -> None:
                """When Furhat finishes speaking, resume listening for the user."""
                try:
                    await client_ws.send_json({"type": "furhat_speak_end"})
                    await furhat.request_audio_start(
                        sample_rate=24000, microphone=True, speaker=False
                    )
                except Exception:
                    pass

            # microphone audio from Furhat
            furhat.add_handler(Events.response_audio_data, on_furhat_audio)
            furhat.add_handler(Events.response_speak_end, on_furhat_speak_end)

            # ── OpenAI message handler ────────────────────────────────────

            async def handle_openai_messages() -> None:
                nonlocal output_started
                try:
                    async for raw in openai_ws:
                        event = json.loads(raw)
                        etype = event.get("type", "")
                        logger.debug("OpenAI → %s", etype)

                        if etype == "session.created":
                            # Configure session: audio in/out, server VAD
                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "session.update",
                                        "session": {
                                            "modalities": ["text", "audio"],
                                            "instructions": SYSTEM_INSTRUCTIONS,
                                            "input_audio_format": "pcm16",
                                            "output_audio_format": "pcm16",
                                            "input_audio_transcription": {
                                                "model": "whisper-1"
                                            },
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
                            # Attend to nearest user and start the conversation
                            await furhat.request_attend_user()
                            await openai_ws.send(
                                json.dumps({"type": "response.create"})
                            )
                            await client_ws.send_json({"type": "connected"})
                            logger.info("Bridge session started (Furhat: %s)", furhat_ip)

                        elif etype == "response.created":
                            # OpenAI is generating – stop the microphone while it speaks
                            await furhat.request_audio_stop()

                        elif etype == "input_audio_buffer.speech_started":
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

                        elif etype == "response.audio.delta":
                            delta = event.get("delta", "")
                            if delta:
                                # output_started is only modified within this sequential
                                # async-for loop (single-threaded async context), so no
                                # synchronisation primitive is needed.
                                if not output_started:
                                    await furhat.request_speak_audio_start(
                                        sample_rate=24000, lipsync=True
                                    )
                                    output_started = True
                                await furhat.request_speak_audio_data(delta)

                        elif etype == "response.audio.done":
                            if output_started:
                                await furhat.request_speak_audio_end()
                                output_started = False

                        elif etype == "response.audio_transcript.delta":
                            await client_ws.send_json(
                                {
                                    "type": "transcript_delta",
                                    "role": "assistant",
                                    "delta": event.get("delta", ""),
                                }
                            )

                        elif etype == "response.audio_transcript.done":
                            transcript = event.get("transcript", "")
                            if transcript:
                                await client_ws.send_json(
                                    {
                                        "type": "transcript",
                                        "role": "assistant",
                                        "text": transcript,
                                    }
                                )
                                logger.info("Assistant: %.80s", transcript)

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

            async def handle_client_messages() -> None:
                """Wait for the browser to disconnect."""
                try:
                    while not stop.is_set():
                        try:
                            msg = await client_ws.receive()
                        except WebSocketDisconnect:
                            break
                        if msg.get("type") == "websocket.disconnect":
                            break
                except WebSocketDisconnect:
                    pass
                finally:
                    stop.set()

            tasks = [
                asyncio.create_task(handle_openai_messages()),
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
    finally:
        try:
            await furhat.request_audio_stop()
            await furhat.request_speak_stop()
        except Exception:
            pass
        try:
            await furhat.disconnect()
        except Exception:
            pass
