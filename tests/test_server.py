"""Tests for the FastAPI server endpoints and WebSocket validation logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_index_returns_200(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200


def test_index_content_type_html(client: TestClient) -> None:
    response = client.get("/")
    assert "text/html" in response.headers["content-type"]


def test_static_index_html_served(client: TestClient) -> None:
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_unknown_path_returns_404(client: TestClient) -> None:
    response = client.get("/does-not-exist")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# WebSocket – config validation (no network calls needed)
# ---------------------------------------------------------------------------


def test_ws_wrong_first_message_type(client: TestClient) -> None:
    """Sending a non-config type as the first WS message returns an error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello"})
        data = ws.receive_json()
    assert data["type"] == "error"
    assert "config" in data["message"].lower()


def test_ws_missing_furhat_ip(client: TestClient) -> None:
    """Config message with empty furhat_ip returns a validation error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "config", "furhat_ip": "", "openai_api_key": "sk-test"})
        data = ws.receive_json()
    assert data["type"] == "error"
    assert "furhat_ip" in data["message"]


def test_ws_missing_openai_key(client: TestClient) -> None:
    """Config message with empty openai_api_key returns a validation error."""
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            {"type": "config", "furhat_ip": "192.168.1.10", "openai_api_key": ""}
        )
        data = ws.receive_json()
    assert data["type"] == "error"
    assert "openai_api_key" in data["message"]


# ---------------------------------------------------------------------------
# WebSocket – run_bridge entry (Furhat connection mocked)
# ---------------------------------------------------------------------------


def test_ws_furhat_connect_failure(client: TestClient) -> None:
    """When Furhat is unreachable the server forwards an error to the client."""
    mock_furhat = MagicMock()
    mock_furhat.connect = AsyncMock(side_effect=ConnectionRefusedError("unreachable"))

    with patch("furhat_bridge.server.AsyncFurhatClient", return_value=mock_furhat):
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "config",
                    "furhat_ip": "10.0.0.1",
                    "openai_api_key": "sk-test",
                }
            )
            # First message is a status update about connecting to Furhat
            status_msg = ws.receive_json()
            assert status_msg["type"] == "status"
            # Second message is the error from the failed connect
            error_msg = ws.receive_json()
    assert error_msg["type"] == "error"
    assert "furhat" in error_msg["message"].lower()


def test_ws_furhat_connect_called_with_ip(client: TestClient) -> None:
    """AsyncFurhatClient is instantiated with the IP provided in the config."""
    furhat_ip = "192.168.50.50"

    mock_furhat = MagicMock()
    mock_furhat.connect = AsyncMock(side_effect=RuntimeError("stop here"))

    with patch(
        "furhat_bridge.server.AsyncFurhatClient", return_value=mock_furhat
    ) as MockClient:
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "config",
                    "furhat_ip": furhat_ip,
                    "openai_api_key": "sk-test",
                }
            )
            ws.receive_json()  # status
            ws.receive_json()  # error

    MockClient.assert_called_once_with(furhat_ip)
