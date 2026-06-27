"""Tests for the native System Gateway CLI."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from system_gateway.cli.main import (
    _cmd_capabilities,
    _cmd_doctor,
    _cmd_pair,
    _cmd_status,
    _cmd_update,
    _default_config_dir,
    _ensure_secret_file,
    _read_secret_file,
    build_parser,
    main,
)
from system_gateway.state import SERVICE_VERSION


class _Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_build_parser_default_run():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.command is None


def test_build_parser_subcommands():
    parser = build_parser()
    for cmd in ("status", "doctor", "capabilities", "logs", "pair", "install", "uninstall", "update", "run"):
        args = parser.parse_args([cmd])
        assert args.command == cmd


def test_read_secret_file_missing(tmp_path: Path):
    assert _read_secret_file(tmp_path / "does-not-exist") is None


def test_read_secret_file_present(tmp_path: Path):
    path = tmp_path / "secret"
    path.write_text(" s3cret ", encoding="utf-8")
    assert _read_secret_file(path) == "s3cret"


def test_ensure_secret_file_restricts_permissions(tmp_path: Path):
    path = tmp_path / "secret"
    _ensure_secret_file(path, "s3cret")
    assert path.read_text(encoding="utf-8") == "s3cret"
    if sys.platform.startswith("linux") or sys.platform == "darwin":
        assert oct(path.stat().st_mode)[-3:] == "600"


def test_pair_generates_secret_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_SHARED_SECRET", "")
    secret_file = tmp_path / "secret"
    args = _Namespace(secret_file=str(secret_file), force=False)
    assert _cmd_pair(args) == 0
    secret = _read_secret_file(secret_file)
    assert secret
    assert len(secret) >= 32


def test_pair_refuses_to_overwrite_without_force(tmp_path: Path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("existing", encoding="utf-8")
    args = _Namespace(secret_file=str(secret_file), force=False)
    assert _cmd_pair(args) == 2


def test_pair_overwrites_with_force(tmp_path: Path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("existing", encoding="utf-8")
    args = _Namespace(secret_file=str(secret_file), force=True)
    assert _cmd_pair(args) == 0
    assert _read_secret_file(secret_file) != "existing"


def test_status_reports_health(monkeypatch):
    health = {
        "status": "ok",
        "service": "system_gateway",
        "version": SERVICE_VERSION,
        "uptime": 123,
        "platform": "linux",
    }
    monkeypatch.setattr(
        "system_gateway.cli.main._http_get_json", lambda url: health
    )
    args = _Namespace(url="http://gw")
    assert _cmd_status(args) == 0


def test_capabilities_reports_json(monkeypatch, capsys):
    caps = {"platform": "linux", "structured_actions": ["system.status"]}
    monkeypatch.setattr(
        "system_gateway.cli.main._http_get_json", lambda url: caps
    )
    args = _Namespace(url="http://gw")
    assert _cmd_capabilities(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == caps


def test_doctor_warns_without_secret(monkeypatch, capsys):
    health = {"status": "ok", "version": SERVICE_VERSION, "platform": "linux", "uptime": 1}
    caps = {"platform": "linux", "raw_shell": True, "shells": ["/bin/sh"], "structured_actions": []}
    call_count = {"count": 0}

    def fake_get(url):
        call_count["count"] += 1
        if "health" in url:
            return health
        return caps

    monkeypatch.setattr("system_gateway.cli.main._http_get_json", fake_get)
    monkeypatch.delenv("SYSTEM_GATEWAY_SHARED_SECRET", raising=False)
    monkeypatch.delenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE", raising=False)
    args = _Namespace(url="http://gw")
    assert _cmd_doctor(args) == 2
    captured = capsys.readouterr()
    assert "No SYSTEM_GATEWAY_SHARED_SECRET" in captured.out


def test_update_rejects_without_secret(monkeypatch, capsys):
    monkeypatch.delenv("SYSTEM_GATEWAY_SHARED_SECRET", raising=False)
    monkeypatch.delenv("SYSTEM_GATEWAY_SHARED_SECRET_FILE", raising=False)
    args = _Namespace(url="http://gw", target_version=None, from_version=None)
    assert _cmd_update(args) == 1
    captured = capsys.readouterr()
    assert "SYSTEM_GATEWAY_SHARED_SECRET is required" in captured.err


def test_update_sends_approved_request(monkeypatch, capsys):
    monkeypatch.setenv("SYSTEM_GATEWAY_SHARED_SECRET", "test-secret")
    response = {"ok": True, "message": "queued"}

    class _FakeResponse:
        def read(self):
            return json.dumps(response).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    opened = []

    def fake_urlopen(req, timeout):
        opened.append({"url": req.full_url, "data": req.data, "req": req})
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("urllib.request.Request", lambda *a, **kw: _Namespace(full_url=a[0], data=kw.get("data"), headers=kw.get("headers", {})))

    args = _Namespace(url="http://gw", target_version="0.2.0", from_version=SERVICE_VERSION)
    assert _cmd_update(args) == 0
    assert len(opened) == 1
    sent_headers = opened[0]["req"].headers
    assert "X-System-Gateway-Signature" in sent_headers
    assert "X-System-Gateway-Timestamp" in sent_headers
    assert "X-System-Gateway-Nonce" in sent_headers
    assert sent_headers["X-System-Gateway-Actor"] == "owner-cli"
    payload = json.loads(opened[0]["data"])
    assert payload["from_version"] == SERVICE_VERSION
    assert payload["to_version"] == "0.2.0"
    assert payload["approval_id"]


def test_main_runs_subcommand(monkeypatch, capsys):
    """``main`` dispatches to subcommands and returns their exit code."""

    health = {"status": "ok", "service": "system_gateway", "version": SERVICE_VERSION, "uptime": 1, "platform": "linux"}
    monkeypatch.setattr("system_gateway.cli.main._http_get_json", lambda url: health)
    assert main(["--url", "http://gw", "status"]) == 0
    assert "Status:" in capsys.readouterr().out


def test_main_default_is_run(monkeypatch):
    """With no args, ``main`` defaults to ``run`` and creates the app."""

    run_called = []

    def fake_run_app(app, host, port):
        run_called.append((host, port))
        raise SystemExit(0)

    monkeypatch.setattr("system_gateway.cli.main.web.run_app", fake_run_app)
    with pytest.raises(SystemExit):
        main([])
    assert run_called == [("127.0.0.1", 8380)]


def test_main_run_uses_config_env(monkeypatch):
    monkeypatch.setenv("SYSTEM_GATEWAY_HOST", "0.0.0.0")
    monkeypatch.setenv("SYSTEM_GATEWAY_PORT", "9999")
    run_called = []

    def fake_run_app(app, host, port):
        run_called.append((host, port))
        raise SystemExit(0)

    monkeypatch.setattr("system_gateway.cli.main.web.run_app", fake_run_app)
    with pytest.raises(SystemExit):
        main(["run"])
    assert run_called == [("0.0.0.0", 9999)]
