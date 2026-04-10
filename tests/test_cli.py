"""Tests for the furhat_bridge CLI entry point."""

import sys
from unittest.mock import patch

import pytest

from furhat_bridge.__main__ import main


# ---------------------------------------------------------------------------
# Argument defaults
# ---------------------------------------------------------------------------


def test_cli_default_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["host"] == "0.0.0.0"


def test_cli_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    _, kwargs = mock_run.call_args
    assert kwargs["port"] == 8000


def test_cli_default_reload_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    _, kwargs = mock_run.call_args
    assert kwargs["reload"] is False


def test_cli_default_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    _, kwargs = mock_run.call_args
    assert kwargs["log_level"] == "info"


# ---------------------------------------------------------------------------
# Custom arguments
# ---------------------------------------------------------------------------


def test_cli_custom_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge", "--host", "127.0.0.1"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    _, kwargs = mock_run.call_args
    assert kwargs["host"] == "127.0.0.1"


def test_cli_custom_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge", "--port", "9000"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    _, kwargs = mock_run.call_args
    assert kwargs["port"] == 9000


def test_cli_reload_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge", "--reload"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    _, kwargs = mock_run.call_args
    assert kwargs["reload"] is True


def test_cli_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge", "--log-level", "debug"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    _, kwargs = mock_run.call_args
    assert kwargs["log_level"] == "debug"


def test_cli_app_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """uvicorn.run receives the correct app import string."""
    monkeypatch.setattr(sys, "argv", ["furhat-bridge"])
    with patch("furhat_bridge.__main__.uvicorn.run") as mock_run:
        main()
    args, _ = mock_run.call_args
    assert args[0] == "furhat_bridge.server:app"


# ---------------------------------------------------------------------------
# --help exits cleanly
# ---------------------------------------------------------------------------


def test_cli_help_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0


def test_cli_invalid_log_level_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["furhat-bridge", "--log-level", "nonsense"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0
