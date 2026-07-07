"""Unit tests for the System Gateway policy model."""
from __future__ import annotations

import pytest

from twin.shared.system_gateway.policy import (
    PolicyContext,
    PolicyReason,
    PolicyVerdict,
    evaluate_action_policy,
    evaluate_shell_policy,
)


def _ctx(approval_id: str | None = None) -> PolicyContext:
    return PolicyContext(actor="march7", action="system.status", approval_id=approval_id)


def test_unknown_action_is_denied():
    decision = evaluate_action_policy(
        action="",
        action_available=True,
        context=_ctx(approval_id="ok"),
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.UNKNOWN_ACTION


def test_unavailable_action_is_denied():
    decision = evaluate_action_policy(
        action="system.status",
        action_available=False,
        context=_ctx(approval_id="ok"),
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.ACTION_NOT_AVAILABLE


def test_action_without_approval_id_requires_approval():
    decision = evaluate_action_policy(
        action="system.status",
        action_available=True,
        context=_ctx(approval_id=None),
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.APPROVAL_REQUIRED
    assert decision.requires_approval is True


def test_action_with_consumed_approval_id_is_denied():
    decision = evaluate_action_policy(
        action="system.status",
        action_available=True,
        context=_ctx(approval_id="dup"),
        consumed_approvals={"dup"},
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.APPROVAL_REPLAYED


def test_action_with_fresh_approval_id_is_allowed():
    decision = evaluate_action_policy(
        action="system.status",
        action_available=True,
        context=_ctx(approval_id="fresh"),
        consumed_approvals={"used"},
    )

    assert decision.verdict is PolicyVerdict.ALLOW
    assert decision.reason is PolicyReason.ALLOWED
    assert decision.approval_id == "fresh"


def test_shell_is_denied_by_default():
    decision = evaluate_shell_policy(
        raw_shell_enabled=False,
        context=_ctx(approval_id="ok"),
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.RAW_SHELL_DISABLED


def test_shell_when_enabled_requires_approval():
    decision = evaluate_shell_policy(
        raw_shell_enabled=True,
        context=_ctx(approval_id=None),
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.APPROVAL_REQUIRED


def test_shell_when_enabled_and_replayed_is_denied():
    decision = evaluate_shell_policy(
        raw_shell_enabled=True,
        context=_ctx(approval_id="dup"),
        consumed_approvals={"dup"},
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.APPROVAL_REPLAYED


@pytest.mark.parametrize(
    "approval_id",
    ["", "   "],
)
def test_blank_approval_id_is_rejected(approval_id: str):
    decision = evaluate_action_policy(
        action="system.status",
        action_available=True,
        context=_ctx(approval_id=approval_id),
    )

    assert decision.verdict is PolicyVerdict.DENY
    assert decision.reason is PolicyReason.APPROVAL_REQUIRED
