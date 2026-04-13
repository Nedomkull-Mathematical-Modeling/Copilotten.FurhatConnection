# Copilotten.FurhatConnection

A FastAPI-based WebSocket bridge between a **Furhat robot** and the **OpenAI Realtime API**.

```
Furhat microphone (PCM16 audio @ 24 kHz)
        │
        ▼
  FastAPI /ws  ──────► OpenAI Realtime API (gpt-4o-realtime-preview)
        │                      │ response.audio.delta → PCM16 audio
        │◄─────────────────────┘
        │ request_speak_audio_start/data/end
        ▼
  Furhat robot (furhat-realtime-api)

Browser (monitor UI)  ◄──── transcripts & status ────  FastAPI /ws
```

## Installation

```bash
pip install furhat-bridge
```

## Quick start

```bash
# Start the bridge server (binds to 0.0.0.0:8000 by default)
furhat-bridge

# Custom host/port
furhat-bridge --host 127.0.0.1 --port 9000

# Development mode with auto-reload
furhat-bridge --reload

# Or with uvicorn directly
uvicorn furhat_bridge.server:app --reload
```

Then open `http://localhost:8000` in your browser, enter the Furhat IP address and your OpenAI API key, and click **Connect**.

## Development (from source)

```bash
# Clone and install in editable mode
git clone https://github.com/Nedomkull-Mathematical-Modeling/Copilotten.FurhatConnection
cd Copilotten.FurhatConnection
pip install -e .

# Or install only the dependencies without packaging
pip install -r requirements.txt
uvicorn main:app --reload
```

## Publishing to PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

## How it works

1. The browser opens a WebSocket to `/ws` and sends a `config` message with the Furhat IP and OpenAI API key.
2. The server connects to the Furhat robot using [`furhat-realtime-api`](https://pypi.org/project/furhat-realtime-api/) (`AsyncFurhatClient`) and to the OpenAI Realtime API via WebSocket.
3. On `session.created`, the server configures the OpenAI session (audio in/out, server-side VAD, Whisper transcription) and triggers an initial greeting from Copilotten.
4. When OpenAI is generating a response, the Furhat microphone is paused. OpenAI's audio deltas are streamed directly to the Furhat robot for real-time lipsync playback.
5. When Furhat finishes speaking (`response.speak.end`), the microphone resumes and the user can speak. The Furhat microphone audio (PCM16, 24 kHz, mono) is forwarded to OpenAI using `input_audio_buffer.append`.
6. OpenAI's server-side VAD detects speech boundaries automatically.
7. Transcripts (both user speech via Whisper and assistant replies) are displayed in the browser in real time.

## Requirements

- Python 3.10+
- A Furhat robot accessible on the local network
- An [OpenAI API key](https://platform.openai.com/api-keys) with access to the Realtime API