from __future__ import annotations

from aiohttp.test_utils import make_mocked_request
import pytest

from system_gateway.config import GatewayConfig
from system_gateway.server import CONFIG_KEY, capabilities, create_app, health


@pytest.mark.asyncio
async def test_health_response() -> None:
    response = await health(make_mocked_request("GET", "/health"))

    assert response.status == 200
    assert response.content_type == "application/json"
    assert response.text == '{"status": "ok", "service": "system_gateway"}'


@pytest.mark.asyncio
async def test_capabilities_response() -> None:
    response = await capabilities(make_mocked_request("GET", "/capabilities"))

    assert response.status == 200
    assert response.content_type == "application/json"
    assert "raw_shell" in response.text


def test_create_app_registers_routes() -> None:
    app = create_app(GatewayConfig(host="0.0.0.0", port=9999))

    route_paths = {
        route.resource.canonical
        for route in app.router.routes()
        if route.resource is not None
    }

    assert app[CONFIG_KEY] == GatewayConfig(host="0.0.0.0", port=9999)
    assert route_paths == {"/health", "/capabilities"}
