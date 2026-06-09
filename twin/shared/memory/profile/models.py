"""Profile (T3) data models — section enum + bullet dataclass."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProfileSection(str, Enum):
    BASIC = "basic"
    CONTACT = "contact"
    RELATIONSHIP = "relationship"
    WORK = "work"
    INTEREST = "interest"
    HABIT = "habit"
    PSYCHOLOGICAL = "psychological"
    RULES = "rules"


@dataclass
class ProfileBullet:
    """A single parsed bullet from a profile section."""
    section: str
    text: str
