"""Compatibility imports for the Evernight A2A boundary."""

from twin.evernight.a2a.handlers import EvernightA2AHandler as _A2AHandler
from twin.evernight.a2a.server import start_server
from twin.evernight.http.dm_routes import DEFAULT_OWNER_USER_ID, EvernightDMRoutes


class EvernightA2AHandler(_A2AHandler, EvernightDMRoutes):
    """Backward-compatible combined handler for old imports."""

    def __init__(
        self,
        agent,
        discord_bot=None,
        owner_user_id: str | int = DEFAULT_OWNER_USER_ID,
    ):
        _A2AHandler.__init__(self, agent)
        EvernightDMRoutes.__init__(
            self,
            discord_bot=discord_bot,
            owner_user_id=owner_user_id,
        )


__all__ = ["DEFAULT_OWNER_USER_ID", "EvernightA2AHandler", "start_server"]
