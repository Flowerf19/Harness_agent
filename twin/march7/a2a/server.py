"""March7 A2A server assembly."""

from twin.march7.a2a.handlers import March7A2AHandler
from twin.march7.agent import March7Agent
from twin.shared.a2a.server import A2AServer


def start_server(agent: March7Agent, host="0.0.0.0", port=8000) -> A2AServer:
    handler = March7A2AHandler(agent)
    return A2AServer(
        agent_card=agent.get_agent_card(),
        skill_handlers={
            "chat": handler.handle_chat_task,
            "get_snapshot": handler.handle_get_snapshot,
            "clear_session": handler.handle_clear_session,
        },
        host=host,
        port=port,
    )
