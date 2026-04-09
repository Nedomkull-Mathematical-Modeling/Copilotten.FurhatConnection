# Copilotten.FurhatConnection

A FastAPI-based WebSocket bridge between a **Furhat robot** and the **OpenAI Realtime API**.

```
Browser mic (PCM16 audio)
        │
        ▼
  FastAPI /ws  ──────► OpenAI Realtime API (gpt-4o-realtime-preview)
        │                      │ response.done → text
        │◄─────────────────────┘
        │ request.speak.text
        ▼
  Furhat robot (ws://<ip>:9000/v1/events)
```

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
uvicorn main:app --reload

# 3. Open http://localhost:8000 in your browser
#    Enter the Furhat IP address and your OpenAI API key, then click Connect.
```

## How it works

1. The browser opens a WebSocket to `/ws` and sends a `config` message with the Furhat IP and OpenAI API key.
2. The server opens WebSocket connections to both the Furhat robot (`ws://<ip>:9000/v1/events`) and the OpenAI Realtime API.
3. Microphone audio (PCM16, 24 kHz, mono) is captured in the browser via the Web Audio API and streamed to the server, which forwards it to OpenAI using `input_audio_buffer.append`.
4. OpenAI's server-side VAD detects speech boundaries automatically.
5. When OpenAI emits `response.done`, the server extracts the assistant's text and sends `request.speak.text` to the Furhat robot so it speaks the response aloud.
6. Transcripts (both user speech and assistant replies) are displayed in the browser in real time.

## Requirements

- Python 3.10+
- A Furhat robot accessible on the local network
- An [OpenAI API key](https://platform.openai.com/api-keys) with access to the Realtime API