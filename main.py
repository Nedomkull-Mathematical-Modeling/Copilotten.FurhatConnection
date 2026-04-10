"""
Development shim – re-exports the FastAPI app from the installable package.

Run with:
    uvicorn main:app --reload

Or use the installed CLI:
    furhat-bridge --reload
"""

from furhat_bridge.server import app  # noqa: F401
