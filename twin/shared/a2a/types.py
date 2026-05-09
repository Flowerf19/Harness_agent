"""A2A (Agent-to-Agent) protocol types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Part:
    type: str  # "text", "data", "file", etc.
    text: Optional[str] = None
    data: Optional[dict] = None
    file_url: Optional[str] = None


@dataclass
class A2AMessage:
    role: str  # "user", "agent"
    parts: List[Part] = field(default_factory=list)
    message_id: Optional[str] = None
    context_id: Optional[str] = None


@dataclass
class A2ATask:
    id: str
    session_id: Optional[str] = None
    skill: Optional[str] = None
    message: Optional[A2AMessage] = None
    status: TaskStatus = TaskStatus.PENDING
    artifacts: List[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentCard:
    name: str
    description: str
    url: str
    version: str = "1.0.0"
    provider: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    skills: List[dict] = field(default_factory=list)
