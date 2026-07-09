"""March7 A2A agent card."""

from twin.shared.a2a.types import AgentCard


def build_agent_card() -> AgentCard:
    return AgentCard(
        name="March7",
        description="Conversational AI agent - friendly and helpful companion",
        url="http://march7:8000",
        version="1.0.0",
        capabilities=["chat", "streaming"],
        skills=[
            {
                "id": "chat",
                "name": "Chat",
                "description": "Conversational chat with memory and tools",
            },
            {
                "id": "get_snapshot",
                "name": "Get Snapshot",
                "description": "Get T1 memory snapshot",
            },
            {
                "id": "clear_session",
                "name": "Clear Session",
                "description": "Clear T1 memory after successful consolidation",
            },
        ],
    )
