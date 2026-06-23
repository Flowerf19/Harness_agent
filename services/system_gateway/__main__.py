"""Command-line entrypoint for the System Gateway service."""

from __future__ import annotations

from aiohttp import web

from .config import GatewayConfig
from .server import create_app


def main() -> None:
    """Run the aiohttp service."""

    config = GatewayConfig.from_env()
    web.run_app(create_app(config), host=config.host, port=config.port)


if __name__ == "__main__":
    main()

