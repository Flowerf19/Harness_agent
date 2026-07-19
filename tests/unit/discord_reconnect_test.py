"""Unit tests for Discord adapter login-time auto-reconnect.

The supervised runner must retry transient network failures (DNS not ready at
container boot) with capped exponential backoff, stop immediately on auth
errors, and propagate cancellation so graceful shutdown still works.
"""
from __future__ import annotations

import asyncio

import pytest

from gateway.adapters.discord.adapter import (
    RECONNECT_BASE_DELAY,
    RECONNECT_MAX_DELAY,
    DiscordPlatformAdapter,
    _is_auth_error,
    _is_network_error,
)


class _FakeBot:
    """Stand-in for discord.py CoreBot that scripts start() outcomes."""

    def __init__(self, outcomes):
        # outcomes: list of Exception (raise) or None (return cleanly).
        self._outcomes = list(outcomes)
        self.start_calls = 0
        self.close_calls = 0
        self.clear_calls = 0

    async def start(self, token, *, reconnect=True):
        self.start_calls += 1
        if not self._outcomes:
            return
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return

    async def close(self):
        self.close_calls += 1

    def clear(self):
        self.clear_calls += 1


def _make_adapter(bot: _FakeBot) -> DiscordPlatformAdapter:
    """Build an adapter without running __init__ side effects (event wiring)."""
    adapter = DiscordPlatformAdapter.__new__(DiscordPlatformAdapter)
    adapter._bot = bot
    adapter._bot_name = "march7"
    adapter._task = None
    return adapter


@pytest.fixture
def no_sleep(monkeypatch):
    """Record backoff delays and skip real waiting."""
    delays: list[float] = []

    async def _fake_sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    return delays


def test_predicates_classify_errors():
    assert _is_network_error(Exception("Temporary failure in name resolution"))
    assert _is_network_error(Exception("Cannot connect to host discord.com [gaierror]"))
    assert not _is_network_error(Exception("token is invalid"))

    assert _is_auth_error(Exception("Improper token has been passed: login failed"))
    assert _is_auth_error(Exception("PrivilegedIntentsRequired: disallowed intent(s)"))
    assert not _is_auth_error(Exception("network is unreachable"))


@pytest.mark.asyncio
async def test_retries_network_failure_until_success(no_sleep):
    # Fail with DNS twice, then connect cleanly.
    bot = _FakeBot([
        OSError("Temporary failure in name resolution"),
        OSError("Temporary failure in name resolution"),
        None,
    ])
    adapter = _make_adapter(bot)

    await adapter._run_supervised("token")

    assert bot.start_calls == 3           # 2 failures + 1 success
    assert bot.close_calls == 2           # reset between each retry
    assert bot.clear_calls == 2
    assert no_sleep == [RECONNECT_BASE_DELAY, RECONNECT_BASE_DELAY * 2]


@pytest.mark.asyncio
async def test_auth_error_stops_without_retry(no_sleep):
    bot = _FakeBot([Exception("Improper token has been passed: login failed")])
    adapter = _make_adapter(bot)

    await adapter._run_supervised("token")

    assert bot.start_calls == 1           # no retry
    assert bot.close_calls == 0
    assert no_sleep == []                 # never slept


@pytest.mark.asyncio
async def test_unknown_error_is_retried(no_sleep):
    bot = _FakeBot([RuntimeError("something weird"), None])
    adapter = _make_adapter(bot)

    await adapter._run_supervised("token")

    assert bot.start_calls == 2
    assert no_sleep == [RECONNECT_BASE_DELAY]


@pytest.mark.asyncio
async def test_backoff_is_capped(no_sleep):
    # 12 consecutive failures then success — delays must plateau at the cap.
    bot = _FakeBot([OSError("name resolution")] * 12 + [None])
    adapter = _make_adapter(bot)

    await adapter._run_supervised("token")

    assert max(no_sleep) == RECONNECT_MAX_DELAY
    assert no_sleep[-1] == RECONNECT_MAX_DELAY
    assert all(d <= RECONNECT_MAX_DELAY for d in no_sleep)


@pytest.mark.asyncio
async def test_cancellation_propagates():
    class _CancellingBot(_FakeBot):
        async def start(self, token, *, reconnect=True):
            self.start_calls += 1
            raise asyncio.CancelledError

    bot = _CancellingBot([])
    adapter = _make_adapter(bot)

    with pytest.raises(asyncio.CancelledError):
        await adapter._run_supervised("token")

    assert bot.start_calls == 1
    assert bot.close_calls == 0           # cancel skips the retry/reset path
