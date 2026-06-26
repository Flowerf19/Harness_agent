"""Linux capability reporting."""
from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import sys
from typing import Any

from .base import (
    CapabilityAction,
    CapabilityAdapter,
    PlatformCapabilities,
    run_with_timeout,
    truncate_output,
)


class LinuxCapabilityAdapter(CapabilityAdapter):
    """Report Linux capabilities and run read-only structured actions.

    ``system.status`` executes via pure-Python (no shell).
    ``system.disk_usage``, ``docker.list_containers``, ``docker.container_logs``,
    and ``service.status`` execute read-only subprocesses with safe arg-lists
    (no ``shell=True``, no string interpolation of user arguments).
    """

    def capabilities(self) -> PlatformCapabilities:
        return PlatformCapabilities(
            platform="linux",
            shells=["/bin/sh"],
            raw_shell=False,
            features=[
                "read_only_capability_report",
                "structured_actions_only",
            ],
            actions=[
                CapabilityAction(
                    name="system.status",
                    description="Read host platform metadata.",
                    read_only=True,
                    available=True,
                ),
                CapabilityAction(
                    name="system.disk_usage",
                    description="Read disk usage via df (read-only subprocess).",
                    read_only=True,
                    available=True,
                ),
                CapabilityAction(
                    name="docker.list_containers",
                    description="List Docker containers via docker ps (read-only subprocess).",
                    read_only=True,
                    available=True,
                ),
                CapabilityAction(
                    name="docker.container_logs",
                    description="Read Docker container logs via docker logs (read-only subprocess).",
                    read_only=True,
                    available=True,
                ),
                CapabilityAction(
                    name="service.status",
                    description="Read systemd service status via systemctl (read-only subprocess).",
                    read_only=True,
                    available=True,
                ),
            ],
            unsupported=["raw_shell"],
            notes=[
                "system.status executes read-only (pure-Python, no shell).",
                "system.disk_usage executes read-only subprocess (df).",
                "docker.list_containers and docker.container_logs execute read-only subprocess (docker).",
                "service.status executes read-only subprocess (systemctl).",
                "Mutating and shell actions remain gated behind policy + approval.",
            ],
        )

    async def run_action(
        self,
        action: str,
        arguments: dict[str, Any],
        *,
        timeout: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        if action == "system.status":
            return self._system_status(max_output_chars)
        if action == "system.disk_usage":
            return await self._disk_usage(arguments, timeout, max_output_chars)
        if action == "docker.list_containers":
            return await self._docker_list_containers(arguments, timeout, max_output_chars)
        if action == "docker.container_logs":
            return await self._docker_container_logs(arguments, timeout, max_output_chars)
        if action == "service.status":
            return await self._service_status(arguments, timeout, max_output_chars)
        return await super().run_action(
            action, arguments, timeout=timeout, max_output_chars=max_output_chars
        )

    # --- helpers ---

    @staticmethod
    def _validate_path(value: str) -> bool:
        """Return True if *value* is an absolute path free of shell metacharacters."""
        if not value.startswith("/"):
            return False
        # Reject paths that contain characters commonly used for shell injection.
        if re.search(r'[;|&`$(){}[\]<>\\\n\r]', value):
            return False
        return True

    @staticmethod
    def _validate_name(value: str) -> bool:
        """Return True if *value* matches ^[a-zA-Z0-9_.-]+$ and length <= 128."""
        if len(value) > 128:
            return False
        return bool(re.fullmatch(r"[a-zA-Z0-9_.-]+", value))

    @staticmethod
    async def _run_cmd(args: list[str], timeout: int) -> dict[str, Any]:
        """Run *args* via ``asyncio.create_subprocess_exec`` with stdout/stderr PIPE.

        Returns a dict with ``stdout``, ``stderr``, ``returncode``, and
        ``timed_out``. A missing executable is surfaced as returncode 127 so
        callers can decide how to report it instead of raising through the
        request handler.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": f"{args[0]}: command not found",
                "returncode": 127,
                "timed_out": False,
            }
        try:
            stdout_bytes, stderr_bytes = await run_with_timeout(
                lambda: proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"stdout": "", "stderr": "", "returncode": -1, "timed_out": True}
        return {
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "returncode": proc.returncode,
            "timed_out": False,
        }

    # --- actions ---

    @staticmethod
    def _system_status(max_output_chars: int) -> dict[str, Any]:
        """Gather host metadata via pure-Python, read-only, no-shell calls."""

        uname = platform.uname()
        data: dict[str, Any] = {
            "platform": platform.platform(),
            "system": uname.system,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "node": uname.node,
            "python_version": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
        }
        try:
            load1, load5, load15 = os.getloadavg()
            data["load_average"] = [round(load1, 2), round(load5, 2), round(load15, 2)]
        except (OSError, AttributeError):
            data["load_average"] = None

        output = truncate_output(
            "\n".join(f"{key}: {value}" for key, value in data.items()),
            max_output_chars,
        )
        return {
            "ok": True,
            "output": output,
            "error": None,
            "exit_code": 0,
            "data": data,
        }

    async def _disk_usage(
        self,
        arguments: dict[str, Any],
        timeout: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        """Run ``df`` for the given path and parse its output."""

        path = arguments.get("path", "/")
        detail = arguments.get("detail", False)

        if not self._validate_path(path):
            return {
                "ok": False,
                "output": "",
                "error": "invalid_path",
                "exit_code": None,
                "data": {},
            }

        flag = "-B1" if detail else "-h"
        result = await self._run_cmd(["df", flag, path], timeout=timeout)

        if result["timed_out"]:
            return {
                "ok": False,
                "output": "",
                "error": "timed_out",
                "exit_code": -1,
                "data": {},
            }

        stdout = result["stdout"]
        stderr = result["stderr"]
        returncode = result["returncode"]

        output = truncate_output(stdout or stderr, max_output_chars)
        data: dict[str, Any] = {"command": ["df", flag, path]}

        if returncode == 0 and stdout:
            lines = stdout.strip().splitlines()
            if len(lines) >= 2:
                headers = lines[0].split()
                values = lines[1].split()
                data["parsed"] = dict(zip(headers, values))

        return {
            "ok": returncode == 0,
            "output": output,
            "error": None if returncode == 0 else "command_failed",
            "exit_code": returncode,
            "data": data,
        }

    async def _docker_list_containers(
        self,
        arguments: dict[str, Any],
        timeout: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        """Run ``docker ps`` and parse JSON lines."""

        cmd = ["docker", "ps", "--format=json"]
        if arguments.get("all", False):
            cmd.insert(2, "-a")

        result = await self._run_cmd(cmd, timeout=timeout)

        if result["timed_out"]:
            return {
                "ok": False,
                "output": "",
                "error": "timed_out",
                "exit_code": -1,
                "data": {},
            }

        stdout = result["stdout"]
        stderr = result["stderr"]
        returncode = result["returncode"]

        # docker not available
        if returncode != 0 and (
            returncode == 127
            or "not found" in stderr.lower()
            or "No such file" in stderr
        ):
            return {
                "ok": False,
                "output": "",
                "error": "docker_not_available",
                "exit_code": returncode,
                "data": {},
            }

        containers: list[dict[str, Any]] = []
        if returncode == 0 and stdout:
            for line in stdout.strip().splitlines():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        output = truncate_output(
            json.dumps(containers, indent=2) if containers else (stdout or stderr),
            max_output_chars,
        )

        return {
            "ok": returncode == 0,
            "output": output,
            "error": None if returncode == 0 else "command_failed",
            "exit_code": returncode,
            "data": {"containers": containers, "command": cmd},
        }

    async def _docker_container_logs(
        self,
        arguments: dict[str, Any],
        timeout: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        """Run ``docker logs`` for a given container."""

        name_or_id = arguments.get("name_or_id", "")
        tail = max(1, min(int(arguments.get("tail", 50)), 500))
        timestamps = arguments.get("timestamps", False)

        if not self._validate_name(name_or_id):
            return {
                "ok": False,
                "output": "",
                "error": "invalid_container_name",
                "exit_code": None,
                "data": {},
            }

        cmd = ["docker", "logs", "--tail", str(tail)]
        if timestamps:
            cmd.append("--timestamps")
        cmd.append(name_or_id)

        result = await self._run_cmd(cmd, timeout=timeout)

        if result["timed_out"]:
            return {
                "ok": False,
                "output": "",
                "error": "timed_out",
                "exit_code": -1,
                "data": {},
            }

        stdout = result["stdout"]
        stderr = result["stderr"]
        returncode = result["returncode"]

        # docker not available
        if returncode != 0 and (
            returncode == 127
            or "not found" in stderr.lower()
            or "No such file" in stderr
        ):
            return {
                "ok": False,
                "output": "",
                "error": "docker_not_available",
                "exit_code": returncode,
                "data": {},
            }

        output = truncate_output(stdout or stderr, max_output_chars)
        return {
            "ok": returncode == 0,
            "output": output,
            "error": None if returncode == 0 else "command_failed",
            "exit_code": returncode,
            "data": {"command": cmd},
        }

    async def _service_status(
        self,
        arguments: dict[str, Any],
        timeout: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        """Run ``systemctl status`` for a given service."""

        service_name = arguments.get("service_name", "")

        if not self._validate_name(service_name):
            return {
                "ok": False,
                "output": "",
                "error": "invalid_service_name",
                "exit_code": None,
                "data": {},
            }

        cmd = ["systemctl", "status", service_name, "--no-pager"]
        result = await self._run_cmd(cmd, timeout=timeout)

        if result["returncode"] == 127:
            return {
                "ok": False,
                "output": "",
                "error": "systemctl_not_available",
                "exit_code": None,
                "data": {},
            }

        if result["timed_out"]:
            return {
                "ok": False,
                "output": "",
                "error": "timed_out",
                "exit_code": -1,
                "data": {},
            }

        stdout = result["stdout"]
        stderr = result["stderr"]
        returncode = result["returncode"]

        output = truncate_output(stdout or stderr, max_output_chars)
        return {
            "ok": returncode == 0,
            "output": output,
            "error": None if returncode == 0 else "command_failed",
            "exit_code": returncode,
            "data": {"command": cmd},
        }
