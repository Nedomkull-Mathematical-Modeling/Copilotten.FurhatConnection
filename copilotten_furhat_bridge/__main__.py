"""Entry point for `python -m copilotten_furhat_bridge` and the `copilotten-bridge` script."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="copilotten-bridge",
        description="Start the Copilotten Furhat Bridge server.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Log level (default: info)",
    )
    args = parser.parse_args()

    uvicorn.run(
        "copilotten_furhat_bridge.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
