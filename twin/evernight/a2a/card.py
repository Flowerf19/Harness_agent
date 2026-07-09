"""Evernight A2A agent card."""

from twin.shared.a2a.types import AgentCard


def build_agent_card() -> AgentCard:
    return AgentCard(
        name="Evernight",
        description="Memory consolidation and analysis agent",
        url="http://evernight:8001",
        version="1.0.0",
        capabilities=["chat", "consolidation", "streaming"],
        skills=[
            {
                "id": "chat",
                "name": "Chat",
                "description": "Conversational chat with memory and tools",
            },
            {
                "id": "consolidate",
                "name": "Consolidate",
                "description": "Consolidate T1 snapshot into T2 timeline",
            },
            {
                "id": "consolidate_discussion",
                "name": "Consolidate Discussion",
                "description": "Process shared-memory payload into user-centric T2 timeline entries",
            },
        ],
    )
