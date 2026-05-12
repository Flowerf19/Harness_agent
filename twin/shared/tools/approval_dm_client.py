"""ApprovalDMClient — DEPRECATED.

This module is deprecated. Use `twin.shared.tools.dm_client` instead.

Migration:
    from twin.shared.tools.dm_client import DMClient, DMUnavailableError
    # Instead of:
    # from twin.shared.tools.approval_dm_client import ApprovalDMClient, ApprovalDMUnavailableError

ApprovalDMClient is now an alias for DMClient.
ApprovalDMUnavailableError is an alias for DMUnavailableError.
"""
from __future__ import annotations

import warnings

from twin.shared.tools.dm_client import DMClient, DMUnavailableError

warnings.warn(
    "twin.shared.tools.approval_dm_client is deprecated. "
    "Use twin.shared.tools.dm_client instead.",
    DeprecationWarning,
    stacklevel=2,
)


# Backward compatibility aliases
ApprovalDMClient = DMClient
ApprovalDMUnavailableError = DMUnavailableError

__all__ = ["ApprovalDMClient", "ApprovalDMUnavailableError"]
