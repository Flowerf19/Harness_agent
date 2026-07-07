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


def test_linux_capabilities_report_generic_shell() -> None:
    payload = capabilities_payload(LinuxCapabilityAdapter())

    assert payload["service"] == "system_gateway"
    assert payload["platform"] == "linux"
    assert payload["shells"] == ["/bin/sh"]
    assert payload["raw_shell"] is True
    assert payload["features"] == ["generic_shell_exec"]
    # No structured actions in the generic-shell model.
    assert payload["structured_actions"] == []
    assert payload["action_details"] == []


def test_posix_adapters_report_their_shell() -> None:
    for adapter, expected_shell, expected_platform in (
        (MacOSCapabilityAdapter(), "/bin/zsh", "macos"),
        (WindowsCapabilityAdapter(), "powershell.exe", "windows"),
    ):
        caps = adapter.capabilities().to_dict()
        assert caps["platform"] == expected_platform
        assert caps["shells"] == [expected_shell]
        assert caps["raw_shell"] is True
        assert caps["features"] == ["generic_shell_exec"]


def test_shell_argv_posix_vs_powershell() -> None:
    from system_gateway.adapters.base import CapabilityAdapter

    assert CapabilityAdapter._shell_argv("/bin/sh", "echo hi") == ["/bin/sh", "-c", "echo hi"]
    assert CapabilityAdapter._shell_argv(
        "powershell.exe", "Write-Output hi"
    ) == ["powershell.exe", "-NoProfile", "-Command", "Write-Output hi"]


async def test_linux_run_shell_executes_echo() -> None:
    adapter = LinuxCapabilityAdapter()
    result = await adapter.run_shell("echo hello", timeout=5)
    assert result["ok"] is True
    assert result["output"].strip() == "hello"
    assert result["exit_code"] == 0
    assert result["data"]["shell"] == "/bin/sh"