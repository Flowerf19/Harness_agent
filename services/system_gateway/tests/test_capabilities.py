from __future__ import annotations

from system_gateway.capabilities import capabilities_payload, select_adapter
from system_gateway.adapters.linux import LinuxCapabilityAdapter
from system_gateway.adapters.macos import MacOSCapabilityAdapter
from system_gateway.adapters.windows import WindowsCapabilityAdapter


def test_select_adapter_for_known_platforms() -> None:
    assert isinstance(select_adapter("linux"), LinuxCapabilityAdapter)
    assert isinstance(select_adapter("darwin"), MacOSCapabilityAdapter)
    assert isinstance(select_adapter("win32"), WindowsCapabilityAdapter)


def test_unknown_platform_reports_unsupported() -> None:
    capabilities = select_adapter("freebsd").capabilities().to_dict()

    assert capabilities["platform"] == "freebsd"
    assert capabilities["shells"] == []
    assert capabilities["raw_shell"] is False
    assert capabilities["features"] == [
        "read_only_capability_report",
        "unsupported_platform",
    ]


def test_linux_capabilities_are_read_only_metadata() -> None:
    payload = capabilities_payload(LinuxCapabilityAdapter())

    assert payload["service"] == "system_gateway"
    assert payload["platform"] == "linux"
    assert payload["raw_shell"] is False
    assert payload["structured_actions"] == []
    assert all(action["read_only"] is True for action in payload["action_details"])


def test_stub_adapters_do_not_report_available_execution() -> None:
    for adapter in (MacOSCapabilityAdapter(), WindowsCapabilityAdapter()):
        capabilities = adapter.capabilities().to_dict()

        assert capabilities["raw_shell"] is False
        assert capabilities["features"] == [
            "read_only_capability_report",
            "stub_adapter",
        ]
        assert all(action["available"] is False for action in capabilities["action_details"])
