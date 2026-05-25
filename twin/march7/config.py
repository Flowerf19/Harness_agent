"""March7 Agent configuration."""
import os
from dataclasses import dataclass, field


@dataclass
class March7Config:
    port: int = 8000
    redis_db: int = 0
    persona_path: str = "twin/march7/personas"
    agent_name: str = "march7"
    poll_interval: int = 60

    @classmethod
    def from_env(cls) -> "March7Config":
        return cls(
            port=int(os.getenv("MARCH7_A2A_PORT", "8000")),
            redis_db=int(os.getenv("MARCH7_REDIS_DB", "0")),
            persona_path=os.getenv("MARCH7_PERSONA_PATH", "twin/march7/personas"),
            agent_name=os.getenv("AGENT_NAME", "march7"),
            poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
        )
