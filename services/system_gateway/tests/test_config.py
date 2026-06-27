"""Tests for System Gateway runtime configuration."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from system_gateway.config import GatewayConfig


def test_from_env_defaults():
    config = GatewayConfig.from_env()
    assert config.host == "127.0.0.1"
    assert config.port == 8380
    # Generic shell execution is the default path; approval is the control.
    assert config.raw_shell_enabled is True
    assert config.shared_secret is None


def test_from_env_can_disable_raw_shell(monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_RAW_SHELL", "false")
    config = GatewayConfig.from_env()
    assert config.raw_shell_enabled is False


def test_from_env_reads_secret_file(monkeypatch, tmp_path: Path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("file-secret\n", encoding="utf-8")
    monkeypatch.setenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE", str(secret_file))
    monkeypatch.delenv("SYSTEM_GATEWAY_SHARED_SECRET", raising=False)
    config = GatewayConfig.from_env()
    assert config.shared_secret == "file-secret"


def test_env_secret_overrides_file_secret(monkeypatch, tmp_path: Path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("file-secret\n", encoding="utf-8")
    monkeypatch.setenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("SYSTEM_GATEWAY_SHARED_SECRET", "env-secret")
    config = GatewayConfig.from_env()
    assert config.shared_secret == "env-secret"


def test_missing_secret_file_falls_back_to_none(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("SYSTEM_GATEWAY_SHARED_SECRET", raising=False)
    config = GatewayConfig.from_env()
    assert config.shared_secret is None


def test_from_env_custom_host_port(monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_HOST", "0.0.0.0")
    monkeypatch.setenv("SYSTEM_GATEWAY_PORT", "9999")
    monkeypatch.setenv("SYSTEM_GATEWAY_RAW_SHELL", "true")
    config = GatewayConfig.from_env()
    assert config.host == "0.0.0.0"
    assert config.port == 9999
    assert config.raw_shell_enabled is True


def test_parse_port_invalid(monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_PORT", "not-a-port")
    with pytest.raises(ValueError, match="integer"):
        GatewayConfig.from_env()


def test_parse_port_out_of_range(monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_PORT", "70000")
    with pytest.raises(ValueError, match="between 1 and 65535"):
        GatewayConfig.from_env()
