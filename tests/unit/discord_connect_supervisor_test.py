"""Tests for the Discord connect supervisor and A2A health probe."""
from __future__ import annotations

import asyncio
import json
import ssl

import aiohttp
import pytest
from unittest import mock

import discord

from gateway.adapters.discord.connect import (
    DEFAULT_MAX_RETRIES,
    describe_error,
    is_fatal,
    supervise_bot,
)
from twin.shared.a2a.server import A2AServer
from twin.shared.a2a.types import AgentCard


def _cert_error() -> aiohttp.ClientConnectorCertificateError:
    """The exact failure seen when booting before NTP has synced the clock."""
    return aiohttp.ClientConnectorCertificateError(
        mock.Mock(connection_key=("discord.com", 443, True)),
        ssl.SSLCertVerificationError("certificate verify failed: certificate is not yet valid"),
    )


class FakeBot:
    """Minimal stand-in for ``commands.Bot`` as used by the supervisor."""

    def __init__(self, failures: list[BaseException | None]) -> None:
        # None entry == start() returns normally (clean stop).
        self._failures = failures
        self.calls = 0
        self.resets = 0
        self.http = mock.Mock()
        self.http.close = mock.AsyncMock()

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        self.calls += 1
        failure = self._failures[min(self.calls, len(self._failures)) - 1]
        if failure is not None:
            raise failure

    def clear(self) -> None:
        self.resets += 1


class ClearRaisingBot(FakeBot):
    """``clear()`` raises until the first login got far enough to build state."""

    def clear(self) -> None:
        self.resets += 1
        raise AttributeError("'_MissingSentinel' object has no attribute 'clear'")


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def test_certificate_error_is_retryable():
    assert not is_fatal(_cert_error())


def test_login_failure_is_fatal():
    assert is_fatal(discord.LoginFailure("Improper token has been passed."))
    assert is_fatal(discord.PrivilegedIntentsRequired(" shards"))


def test_describe_error_names_the_exception_class():
    assert describe_error(_cert_error()).startswith("ClientConnectorCertificateError")


# ---------------------------------------------------------------------------
# Supervision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retries_until_connect_succeeds(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("gateway.adapters.discord.connect._sleep", fake_sleep)

    bot = FakeBot([_cert_error(), _cert_error(), None])
    await supervise_bot(bot, "token", name="march7")

    assert bot.calls == 3
    assert bot.resets == 2, "must reset HTTP state between attempts"
    assert sleeps == [2.0, 4.0]


@pytest.mark.asyncio
async def test_stops_retrying_on_fatal_error(monkeypatch):
    async def fake_sleep(delay):
        raise AssertionError("must not sleep/retry after a fatal error")

    monkeypatch.setattr("gateway.adapters.discord.connect._sleep", fake_sleep)

    bot = FakeBot([discord.LoginFailure("Improper token has been passed.")])
    await supervise_bot(bot, "token", name="march7")

    assert bot.calls == 1


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts(monkeypatch):
    async def fake_sleep(delay):
        pass

    monkeypatch.setattr("gateway.adapters.discord.connect._sleep", fake_sleep)

    failures = [_cert_error()] * (DEFAULT_MAX_RETRIES + 1)
    bot = FakeBot(failures)
    await supervise_bot(bot, "token", name="march7", max_retries=3)

    assert bot.calls == 4, "first try plus max_retries retries"


@pytest.mark.asyncio
async def test_cancellation_propagates():
    class HangingBot(FakeBot):
        async def start(self, token: str, *, reconnect: bool = True) -> None:
            self.calls += 1
            await asyncio.sleep(3600)

    bot = HangingBot([None])
    task = asyncio.create_task(supervise_bot(bot, "token", name="march7"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_connector_reset_despite_clear_raising(monkeypatch):
    """A raising ``clear()`` must not strand the closed connector.

    discord.py sets ``bot.http.connector`` once on login and reuses it, while
    closing the session closes that shared connector — so if the reset is
    skipped every later attempt dies with "Session is closed" and the retry
    loop becomes useless.
    """
    from discord.utils import MISSING

    async def fake_sleep(delay):
        pass

    monkeypatch.setattr("gateway.adapters.discord.connect._sleep", fake_sleep)

    bot = ClearRaisingBot([_cert_error()] * 4)
    await supervise_bot(bot, "token", name="march7", max_retries=3)

    assert bot.calls == 4, "kept retrying even though clear() raised"
    assert bot.http.close.await_count == 3
    assert bot.http.connector is MISSING


# ---------------------------------------------------------------------------
# A2A /health endpoint
# ---------------------------------------------------------------------------


def _server(health_probe=None) -> A2AServer:
    async def handler(params):
        yield  # pragma: no cover - not invoked here

    return A2AServer(
        agent_card=AgentCard(name="test", description="", url="", version="1"),
        skill_handlers={"chat": handler},
        health_probe=health_probe,
    )


def _payload(response) -> dict:
    return json.loads(response.text)


@pytest.mark.asyncio
async def test_health_reports_connected_adapter():
    response = await _server(lambda: True)._handle_health(mock.Mock())
    assert response.status == 200
    assert _payload(response) == {"status": "ok", "connected": True}


@pytest.mark.asyncio
async def test_health_reports_disconnected_adapter_as_unreachable():
    response = await _server(lambda: False)._handle_health(mock.Mock())
    assert response.status == 503
    assert _payload(response) == {"status": "degraded", "connected": False}


@pytest.mark.asyncio
async def test_health_defaults_to_ok_without_probe():
    response = await _server()._handle_health(mock.Mock())
    assert response.status == 200
    assert _payload(response) == {"status": "ok", "connected": True}


@pytest.mark.asyncio
async def test_agent_card_route_and_health_route_are_registered():
    app = _server().build_app()
    paths = {resource.canonical for resource in app.router.resources()}
    assert "/health" in paths
    assert "/.well-known/agent.json" in paths
