"""Tests for the one-command System Gateway bootstrap script."""
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_system_gateway.py"


def _load_bootstrap_module():
    spec = importlib.util.spec_from_file_location("bootstrap_system_gateway", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ensure_venv_uses_system_site_packages(monkeypatch, tmp_path: Path):
    bootstrap = _load_bootstrap_module()
    monkeypatch.setattr(bootstrap, "VENV", str(tmp_path / "venv"))
    created = []

    def fake_create(path, *, with_pip, clear, system_site_packages):
        created.append(
            {
                "path": path,
                "with_pip": with_pip,
                "clear": clear,
                "system_site_packages": system_site_packages,
            }
        )
        bootstrap.venv_python(path).parent.mkdir(parents=True, exist_ok=True)
        bootstrap.venv_python(path).write_text("python", encoding="utf-8")

    monkeypatch.setattr(bootstrap.venv, "create", fake_create)

    assert bootstrap.ensure_venv() == tmp_path / "venv"
    assert created == [
        {
            "path": tmp_path / "venv",
            "with_pip": True,
            "clear": False,
            "system_site_packages": True,
        }
    ]


def test_gateway_install_on_windows_prints_foreground_command(monkeypatch, tmp_path: Path):
    bootstrap = _load_bootstrap_module()
    monkeypatch.setattr(bootstrap, "IS_WIN", True)
    monkeypatch.setattr(bootstrap, "IS_LINUX", False)
    monkeypatch.setattr(bootstrap, "IS_MAC", False)
    calls = []
    messages = []
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(bootstrap, "info", messages.append)

    bootstrap.gateway_install(tmp_path / "venv")

    assert calls == []
    assert any("foreground" in message for message in messages)


def test_gateway_install_on_linux_runs_cli_install(monkeypatch, tmp_path: Path):
    bootstrap = _load_bootstrap_module()
    monkeypatch.setattr(bootstrap, "IS_WIN", False)
    monkeypatch.setattr(bootstrap, "IS_LINUX", True)
    monkeypatch.setattr(bootstrap, "IS_MAC", False)
    venv_python = bootstrap.venv_python(tmp_path / "venv")
    ran = []

    class _Result:
        returncode = 0

    def fake_run(cmd, env):
        ran.append((cmd, env))
        return _Result()

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    bootstrap.gateway_install(tmp_path / "venv")

    assert ran[0][0] == [str(venv_python), "-m", "system_gateway", "install"]
    assert ran[0][1]["SYSTEM_GATEWAY_HOST"] == bootstrap.HOST
    assert ran[0][1]["SYSTEM_GATEWAY_PORT"] == bootstrap.PORT
