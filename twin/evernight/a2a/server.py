"""Evernight A2A server assembly."""

from twin.evernight.a2a.handlers import EvernightA2AHandler
from twin.evernight.agent import EvernightAgent
from twin.evernight.http.dm_routes import DEFAULT_OWNER_USER_ID, EvernightDMRoutes
from twin.shared.a2a.server import A2AServer


def start_server(
    agent: EvernightAgent,
    host="0.0.0.0",
    port=8001,
    discord_bot=None,
    owner_user_id: str | int = DEFAULT_OWNER_USER_ID,
) -> A2AServer:
    a2a_handler = EvernightA2AHandler(agent)
    dm_routes = EvernightDMRoutes(
        discord_bot=discord_bot,
        owner_user_id=owner_user_id,
    )
    server = A2AServer(
        agent_card=agent.get_agent_card(),
        skill_handlers={
            "chat": a2a_handler.handle_chat_task,
            "consolidate": a2a_handler.handle_consolidate_task,
            "consolidate_discussion": a2a_handler.handle_consolidate_discussion_task,
        },
        host=host,
        port=port,
    )
    original_build_app = server.build_app

    def patched_build_app():
        app = original_build_app()
        app.router.add_post("/dm", dm_routes.handle_dm)
        app.router.add_post("/approval_dm", dm_routes.handle_approval_dm)
        return app

    server.build_app = patched_build_app
    return server
