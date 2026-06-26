"""Policy model for System Gateway requests.

Policy enforcement belongs to the native System Gateway. Agent-side tools use
these types only to describe requested actions and approval context; the native
service is the single source of truth for whether an action runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional


class PolicyVerdict(str, Enum):
    """Outcome of a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"


class PolicyReason(str, Enum):
    """Reason for a deny verdict. Allow verdicts carry reason=ALLOWED."""

    ALLOWED = "allowed"
    UNKNOWN_ACTION = "unknown_action"
    ACTION_NOT_AVAILABLE = "action_not_available"
    RAW_SHELL_DISABLED = "raw_shell_disabled"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_REPLAYED = "approval_replayed"
    APPROVAL_INVALID = "approval_invalid"


@dataclass(frozen=True)
class PolicyDecision:
    """Result of evaluating a request against local policy."""

    verdict: PolicyVerdict
    reason: PolicyReason
    requires_approval: bool = False
    approval_id: Optional[str] = None


@dataclass(frozen=True)
class PolicyContext:
    """Context passed to the policy evaluator.

    The native service fills this in from the request and its environment.
    """

    actor: str = ""
    action: str = ""
    is_raw_shell: bool = False
    approval_id: Optional[str] = None
    capabilities: Mapping[str, object] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Mapping default must be set in __post_init__ because Mapping is
        # immutable; replace if caller passed None.
        if self.capabilities is None:
            object.__setattr__(self, "capabilities", {})


def evaluate_action_policy(
    *,
    action: str,
    action_available: bool,
    context: PolicyContext,
    consumed_approvals: Optional[set[str]] = None,
) -> PolicyDecision:
    """Evaluate a structured action request.

    - Unknown action names are denied (UNKNOWN_ACTION).
    - Actions reported as unavailable by the platform adapter are denied
      (ACTION_NOT_AVAILABLE).
    - All structured actions currently require a fresh approval id unless the
      caller marks the action as not requiring approval in the future.
    - If an approval id has already been consumed (replay), deny with
      APPROVAL_REPLAYED.
    """

    if not action:
        return PolicyDecision(PolicyVerdict.DENY, PolicyReason.UNKNOWN_ACTION)
    if not action_available:
        return PolicyDecision(PolicyVerdict.DENY, PolicyReason.ACTION_NOT_AVAILABLE)
    if context.approval_id is None or not context.approval_id.strip():
        return PolicyDecision(
            PolicyVerdict.DENY,
            PolicyReason.APPROVAL_REQUIRED,
            requires_approval=True,
        )
    consumed = consumed_approvals or set()
    if context.approval_id in consumed:
        return PolicyDecision(
            PolicyVerdict.DENY,
            PolicyReason.APPROVAL_REPLAYED,
        )
    return PolicyDecision(
        PolicyVerdict.ALLOW,
        PolicyReason.ALLOWED,
        requires_approval=True,
        approval_id=context.approval_id,
    )


def evaluate_shell_policy(
    *,
    raw_shell_enabled: bool,
    context: PolicyContext,
    consumed_approvals: Optional[set[str]] = None,
) -> PolicyDecision:
    """Evaluate a raw shell request.

    Raw shell is denied by default. When enabled by configuration it still
    requires a fresh, non-replayed approval id.
    """

    if not raw_shell_enabled:
        return PolicyDecision(PolicyVerdict.DENY, PolicyReason.RAW_SHELL_DISABLED)
    if context.approval_id is None or not context.approval_id.strip():
        return PolicyDecision(
            PolicyVerdict.DENY,
            PolicyReason.APPROVAL_REQUIRED,
            requires_approval=True,
        )
    consumed = consumed_approvals or set()
    if context.approval_id in consumed:
        return PolicyDecision(
            PolicyVerdict.DENY,
            PolicyReason.APPROVAL_REPLAYED,
        )
    return PolicyDecision(
        PolicyVerdict.ALLOW,
        PolicyReason.ALLOWED,
        requires_approval=True,
        approval_id=context.approval_id,
    )
