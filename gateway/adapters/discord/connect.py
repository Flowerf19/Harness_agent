"""Supervision for the Discord ``bot.start()`` task shared by both twin bots.

``discord.Client.start()`` only retries *websocket* drops. Anything that fails
before a websocket exists — login, TLS — raises out of the task and kills the
connection for good, while the process keeps serving A2A and looks healthy.
Cold boot with an unsynchronised clock is the real-world case: the Discord
certificate looks "not yet valid" until NTP steps the clock forward.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord.utils import MISSING

logger = logging.getLogger(__name__)

# NTP normally settles the clock within a couple of minutes; keep retrying well
# past that so a boot-time race cannot permanently silence a bot.
DEFAULT_MAX_RETRIES = 30
BASE_DELAY = 2.0
MAX_DELAY = 60.0

# Indirection so tests can pin the backoff without patching asyncio globally.
_sleep = asyncio.sleep

# Credentials/intent problems never heal on their own — retrying only buries them.
_FATAL_MARKERS = (
    "privileged intent",
    "disallowed intent",
    "improper token",
    "unknown token",
)


def is_fatal(exc: BaseException) -> bool:
    if isinstance(exc, discord.LoginFailure):
        return True
    error_str = str(exc).lower()
    return isinstance(exc, discord.PrivilegedIntentsRequired) or any(
        marker in error_str for marker in _FATAL_MARKERS
    )


def describe_error(exc: BaseException) -> str:
    """One-line error summary for logs (full traceback lives in ``exc_info``)."""
    return f"{exc.__class__.__name__}: {exc}"


async def _reset_bot(bot: Any) -> None:
    """Return *bot* to a state where ``start()`` can be called again.

    ``bot.close()`` must NOT be used here — it sets ``loop = MISSING``, and the
    next ``start()`` then raises. Instead drop only the HTTP session left behind
    by the failed login, reset client state, and force ``static_login()`` to
    build a fresh connector (closing the session closes the shared one).
    """
    try:
        await bot.http.close()
    except Exception:  # noqa: BLE001 - reset is best-effort before a retry
        logger.warning("Discord bot http close() during reset failed", exc_info=True)

    # Deliberately outside clear()'s try: ``clear()`` raises when the client has
    # not finished its first login, and skipping this line would leave the closed
    # connector behind, making every later attempt fail with "Session is closed".
    bot.http.connector = MISSING
    try:
        bot.clear()
    except Exception:  # noqa: BLE001
        logger.warning("Discord bot clear() during reset failed", exc_info=True)


async def supervise_bot(
    bot: Any,
    token: str,
    *,
    name: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    """Run ``bot.start(token)``, restarting it after a retryable failure.

    Returns when the bot stops on its own (``disconnect()`` closes it) or when
    the failure cannot be recovered by retrying.
    """
    attempt = 0
    while True:
        try:
            await bot.start(token)
            logger.info("Discord bot %s stopped", name)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - any start() failure ends the task
            if is_fatal(exc):
                logger.error(
                    "Discord bot %s login failed with an unrecoverable error, "
                    "not retrying: %s",
                    name,
                    describe_error(exc),
                    exc_info=exc,
                )
                return

            attempt += 1
            if attempt > max_retries:
                logger.error(
                    "Discord bot %s gave up after %d retries — last error: %s",
                    name,
                    max_retries,
                    describe_error(exc),
                )
                return

            delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
            logger.warning(
                "Discord bot %s failed to connect (retry %d/%d), retrying in %.0fs: %s",
                name,
                attempt,
                max_retries,
                delay,
                describe_error(exc),
                exc_info=attempt == 1,
            )
            await _reset_bot(bot)
            await _sleep(delay)
