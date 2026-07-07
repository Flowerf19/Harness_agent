"""Audit event names and schema for System Gateway."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping


class AuditOutcome(str, Enum):
    """Outcome category for a System Gateway audit event."""

    REQUESTED = "requested"
    RESOLVED = "resolved"
    STARTED = "started"
    COMPLETED = "completed"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


EVENT_APPROVAL_REQUESTED = "approval.requested"
EVENT_APPROVAL_RESOLVED = "approval.resolved"
EVENT_ACTION_STARTED = "action.started"
EVENT_ACTION_COMPLETED = "action.completed"
EVENT_ACTION_DENIED = "action.denied"
EVENT_ACTION_TIMED_OUT = "action.timed_out"
EVENT_ACTION_FAILED = "action.failed"


@dataclass(frozen=True)
class AuditEvent:
    """Structured audit record emitted by the native System Gateway."""

    event: str
    outcome: AuditOutcome
    timestamp: float
    actor: str = ""
    subject: str = ""
    approval_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event": self.event,
            "outcome": self.outcome.value,
            "timestamp": self.timestamp,
        }
        if self.actor:
            payload["actor"] = self.actor
        if self.subject:
            payload["subject"] = self.subject
        if self.approval_id:
            payload["approval_id"] = self.approval_id
        if self.details:
            payload["details"] = dict(self.details)
        return payload


def audit_event(
    event: str,
    outcome: AuditOutcome,
    *,
    actor: str = "",
    subject: str = "",
    approval_id: str | None = None,
    details: Mapping[str, Any] | None = None,
    timestamp: float | None = None,
) -> AuditEvent:
    """Build an AuditEvent with a default timestamp if not provided."""

    return AuditEvent(
        event=event,
        outcome=outcome,
        timestamp=timestamp if timestamp is not None else time.time(),
        actor=actor,
        subject=subject,
        approval_id=approval_id,
        details=dict(details or {}),
    )
