"""Evernight Agent configuration."""
import os
from dataclasses import dataclass, field


@dataclass
class EvernightConfig:
    port: int = 8001
    redis_db: int = 1
    persona_path: str = "twin/evernight/personas"
    agent_name: str = "evernight"
    march7_url: str = "http://march7:8000"
    inactivity_seconds: int = 1800
    poll_interval: int = 60

    @classmethod
    def from_env(cls) -> "EvernightConfig":
        return cls(
            port=int(os.getenv("EVERNIGHT_A2A_PORT", "8001")),
            redis_db=int(os.getenv("EVERNIGHT_REDIS_DB", "1")),
            persona_path=os.getenv("EVERNIGHT_PERSONA_PATH", "twin/evernight/personas"),
            agent_name=os.getenv("AGENT_NAME", "evernight"),
            march7_url=os.getenv("MARCH7_URL", "http://march7:8000"),
            inactivity_seconds=int(os.getenv("INACTIVITY_SECONDS", "1800")),
            poll_interval=int(os.getenv("POLL_INTERVAL", "60")),
        )
