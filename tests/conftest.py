"""Shared fixtures for the furhat_bridge test suite."""

import pytest
from starlette.testclient import TestClient

from furhat_bridge.server import app


@pytest.fixture()
def client() -> TestClient:
    """Synchronous ASGI test client wrapping the FastAPI app."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
