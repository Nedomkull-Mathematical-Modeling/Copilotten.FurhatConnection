"""
Development shim – re-exports the FastAPI app from the installable package.

Run with:
    uvicorn main:app --reload

Or use the installed CLI:
    copilotten-bridge --reload
"""

from copilotten_furhat_bridge.server import app  # noqa: F401
