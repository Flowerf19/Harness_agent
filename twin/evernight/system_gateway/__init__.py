"""Evernight System Gateway orchestration.

Owns:
- gateway health/capabilities monitoring and degraded-state reporting
- owner-facing status/doctor/update approval commands
- first-run bootstrap hints (one-time installer command)
- post-bootstrap update flow (gated through the gateway updater endpoint)
- replacement for the legacy direct `/execute` self-heal restart path
"""
from twin.evernight.system_gateway.installer import (
    BootstrapHint,
    InstallerAction,
    InstallerCoordinator,
    KNOWN_GOOD_VERSIONS,
    build_bootstrap_hint,
    compare_versions,
)
from twin.evernight.system_gateway.monitor import (
    GatewayMonitor,
    GatewayMonitorStatus,
    GatewaySnapshot,
    RESTART_ALLOWED_CONTAINERS,
)

__all__ = [
    "BootstrapHint",
    "GatewayMonitor",
    "GatewayMonitorStatus",
    "GatewaySnapshot",
    "InstallerAction",
    "InstallerCoordinator",
    "KNOWN_GOOD_VERSIONS",
    "RESTART_ALLOWED_CONTAINERS",
    "build_bootstrap_hint",
    "compare_versions",
]
