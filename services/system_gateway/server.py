"""aiohttp application for the System Gateway scaffold."""

from __future__ import annotations

from aiohttp import web

from .capabilities import capabilities_payload
from .config import GatewayConfig

CONFIG_KEY = web.AppKey("config", GatewayConfig)


async def health(request: web.Request) -> web.Response:
    """Return service health."""

    return web.json_response(
        {
            "status": "ok",
            "service": "system_gateway",
        }
    )


async def capabilities(request: web.Request) -> web.Response:
    """Return read-only platform capability metadata."""

    return web.json_response(capabilities_payload())


def create_app(config: GatewayConfig | None = None) -> web.Application:
    """Create the aiohttp application."""

    app = web.Application()
    app[CONFIG_KEY] = config or GatewayConfig()
    app.router.add_get("/health", health)
    app.router.add_get("/capabilities", capabilities)
    return app
