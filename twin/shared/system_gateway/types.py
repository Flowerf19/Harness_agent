"""Typed request/response models for the System Gateway protocol."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GatewayHealth:
    status: str
    version: str | None = None
    platform: str | None = None
    uptime: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatewayHealth":
        return cls(
            status=str(data.get("status", "unknown")),
            version=_optional_str(data.get("version")),
            platform=_optional_str(data.get("platform")),
            uptime=_optional_int(data.get("uptime")),
        )


@dataclass(frozen=True)
class GatewayCapabilities:
    platform: str
    shells: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    structured_actions: tuple[str, ...] = ()
    raw_shell: bool = False
    unsupported: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatewayCapabilities":
        return cls(
            platform=str(data.get("platform", "unknown")),
            shells=_string_tuple(data.get("shells")),
            features=_string_tuple(data.get("features")),
            structured_actions=_string_tuple(data.get("structured_actions")),
            raw_shell=bool(data.get("raw_shell", False)),
            unsupported=_string_tuple(data.get("unsupported")),
            notes=_string_tuple(data.get("notes")),
        )


@dataclass(frozen=True)
class GatewayShellRequest:
    command: str
    shell: str | None = None
    cwd: str | None = None
    timeout: int = 30
    max_output_chars: int = 8000
    approval_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "command": self.command,
            "timeout": self.timeout,
            "max_output_chars": self.max_output_chars,
        }
        if self.shell:
            payload["shell"] = self.shell
        if self.cwd:
            payload["cwd"] = self.cwd
        if self.approval_id:
            payload["approval_id"] = self.approval_id
        return payload


@dataclass(frozen=True)
class GatewayActionResponse:
    ok: bool
    output: str = ""
    error: str | None = None
    exit_code: int | None = None
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatewayActionResponse":
        return cls(
            ok=bool(data.get("ok", data.get("success", False))),
            output=str(data.get("output", data.get("stdout", "")) or ""),
            error=_optional_str(data.get("error")),
            exit_code=_optional_int(data.get("exit_code")),
            data=dict(data.get("data") or {}),
        )


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if not isinstance(value, (list, tuple)):
        return (str(value),)
    return tuple(str(item) for item in value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
