"""Evernight System Gateway orchestration.

Owns:
- gateway health/capabilities monitoring and degraded-state reporting
- owner-facing status/doctor/update approval commands
- first-run bootstrap hints and owner-approved bootstrap install bridge
- post-bootstrap update flow (gated through the gateway updater endpoint)
- replacement for the legacy direct `/execute` self-heal restart path
"""
from twin.evernight.system_gateway.installer import (
    BootstrapHint,
    BootstrapInstallResult,
    InstallerAction,
    InstallerCoordinator,
    KNOWN_GOOD_VERSIONS,
    LegacyBashExecutorBootstrapBridge,
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
    "BootstrapInstallResult",
    "GatewayMonitor",
    "GatewayMonitorStatus",
    "GatewaySnapshot",
    "InstallerAction",
    "InstallerCoordinator",
    "KNOWN_GOOD_VERSIONS",
    "LegacyBashExecutorBootstrapBridge",
    "RESTART_ALLOWED_CONTAINERS",
    "build_bootstrap_hint",
    "compare_versions",
]
