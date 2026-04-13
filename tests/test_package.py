"""Tests for the furhat_bridge package-level API."""

import furhat_bridge
from furhat_bridge import __version__
from furhat_bridge.server import app


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__  # non-empty


def test_version_semver_format() -> None:
    """Version should be parseable as X.Y.Z."""
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_module_exposes_version() -> None:
    assert furhat_bridge.__version__ == __version__


def test_app_is_fastapi_instance() -> None:
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)


def test_app_title() -> None:
    from furhat_bridge.server import app as server_app

    assert server_app.title == "Furhat Bridge"
