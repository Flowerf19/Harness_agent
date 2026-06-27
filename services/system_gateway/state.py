"""Runtime state for the System Gateway service.

The native service holds shared state (uptime, consumed approvals, seen nonces,
audit log buffer) here so handlers and tests can reach it without singletons.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from twin.shared.system_gateway import NonceStore

logger = logging.getLogger(__name__)

SERVICE_VERSION = "0.1.0"


@dataclass
class GatewayState:
    """Mutable runtime state owned by the gateway service."""

    started_at: float = field(default_factory=time.time)
    raw_shell_enabled: bool = True
    shared_secret: Optional[str] = None
    consumed_approvals: set[str] = field(default_factory=set)
    nonce_store: NonceStore = field(default_factory=NonceStore)
    audit_log: list[dict[str, object]] = field(default_factory=list)

    def uptime_seconds(self) -> int:
        return int(time.time() - self.started_at)

    def record_audit(self, event: dict[str, object]) -> None:
        self.audit_log.append(event)
        if len(self.audit_log) > 500:
            self.audit_log = self.audit_log[-500:]
        # approval_id is a short-lived bearer token; keep it in the in-memory
        # audit_log buffer above but never write it to the log stream.
        logger.info(
            "system_gateway audit %s",
            {k: v for k, v in event.items() if k not in {"details", "approval_id"}},
        )

    def consume_approval(self, key: str) -> bool:
        """Atomically claim a single-use approval key.

        Returns True if the key was unused (and is now consumed), False if it
        had already been consumed (replay). The check-and-add is atomic under
        the GIL for the single-instance in-memory store.
        """

        if key in self.consumed_approvals:
            return False
        self.consumed_approvals.add(key)
        return True
