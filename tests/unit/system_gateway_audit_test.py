"""Unit tests for the System Gateway audit event schema."""
from __future__ import annotations

from twin.shared.system_gateway.audit import (
    AuditEvent,
    AuditOutcome,
    EVENT_ACTION_DENIED,
    audit_event,
)


def test_audit_event_to_dict_includes_only_present_fields():
    event = audit_event(
        EVENT_ACTION_DENIED,
        AuditOutcome.DENIED,
        actor="march7",
        subject="shell",
        approval_id="abc-123",
        details={"reason": "raw_shell_disabled"},
        timestamp=1700000000.0,
    )

    payload = event.to_dict()

    assert payload["event"] == EVENT_ACTION_DENIED
    assert payload["outcome"] == "denied"
    assert payload["timestamp"] == 1700000000.0
    assert payload["actor"] == "march7"
    assert payload["subject"] == "shell"
    assert payload["approval_id"] == "abc-123"
    assert payload["details"] == {"reason": "raw_shell_disabled"}


def test_audit_event_to_dict_omits_empty_optional_fields():
    event = AuditEvent(
        event="x",
        outcome=AuditOutcome.STARTED,
        timestamp=1.0,
    )

    payload = event.to_dict()

    assert "actor" not in payload
    assert "subject" not in payload
    assert "approval_id" not in payload
    assert "details" not in payload


def test_audit_event_factory_assigns_default_timestamp():
    event = audit_event(EVENT_ACTION_DENIED, AuditOutcome.DENIED)

    assert event.timestamp > 0
    assert event.details == {}
