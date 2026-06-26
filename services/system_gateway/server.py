"""aiohttp application for the System Gateway scaffold."""
from __future__ import annotations

import json as jsonlib
import logging
import time
from typing import Any

from aiohttp import web

from .capabilities import capabilities_payload, select_adapter
from .config import GatewayConfig
from .state import SERVICE_VERSION, GatewayState

logger = logging.getLogger(__name__)


CONFIG_KEY: web.AppKey[GatewayConfig] = web.AppKey("config", GatewayConfig)
STATE_KEY: web.AppKey[GatewayState] = web.AppKey("state", GatewayState)


def _state(request: web.Request) -> GatewayState:
    app = getattr(request, "_app", None)
    if app is not None:
        try:
            return app[STATE_KEY]
        except (KeyError, TypeError):
            pass
    return request.app[STATE_KEY]


def _config(request: web.Request) -> GatewayConfig:
    app = getattr(request, "_app", None)
    if app is not None:
        try:
            return app[CONFIG_KEY]
        except (KeyError, TypeError):
            pass
    return request.app[CONFIG_KEY]


async def health(request: web.Request) -> web.Response:
    """Return service health with version, uptime, and platform."""

    state = _state(request)
    platform = capabilities_payload()["platform"]
    return web.json_response(
        {
            "status": "ok",
            "service": "system_gateway",
            "version": SERVICE_VERSION,
            "uptime": state.uptime_seconds(),
            "platform": platform,
        }
    )


async def capabilities(request: web.Request) -> web.Response:
    """Return read-only platform capability metadata."""

    return web.json_response(capabilities_payload())


@web.middleware
async def auth_middleware(
    request: web.Request,
    handler: Any,
) -> web.StreamResponse:
    """Verify HMAC-signed requests on mutating paths.

    Health and capabilities endpoints are public so monitors can poll them
    without a shared secret. Anything that can change host state must carry a
    valid signature.
    """

    path = request.path
    if path in {"/health", "/capabilities"}:
        return await handler(request)

    state = _state(request)
    if not state.shared_secret:
        # Misconfiguration: refuse all mutating requests when no secret is set.
        logger.warning("system_gateway: refusing %s because no shared secret is set", path)
        return web.json_response(
            {"ok": False, "error": "shared secret not configured"}, status=503
        )

    body = await request.read()
    auth = _extract_headers(request)
    from twin.shared.system_gateway.auth import (
        extract_auth_headers,
        is_timestamp_within_skew,
        verify_signature,
    )

    headers = extract_auth_headers(dict(request.headers))
    signature = headers["signature"]
    timestamp = headers["timestamp"]
    nonce = headers["nonce"]
    actor = headers["actor"]

    if not is_timestamp_within_skew(timestamp):
        return web.json_response(
            {"ok": False, "error": "timestamp outside allowed skew"}, status=401
        )

    if not verify_signature(
        state.shared_secret,
        method=request.method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        actor=actor,
        body=body,
        signature=signature,
    ):
        return web.json_response(
            {"ok": False, "error": "invalid signature"}, status=401
        )

    if not state.nonce_store.is_fresh(nonce):
        return web.json_response(
            {"ok": False, "error": "nonce replayed"}, status=401
        )

    request["auth_actor"] = actor or "unknown"
    return await handler(request)


async def run_action(request: web.Request) -> web.Response:
    """Structured action endpoint.

    Enforces auth, an action-bound single-use approval token, and local policy,
    records the audit lifecycle, then executes the action via the platform
    adapter and returns its real output.
    """

    import asyncio

    from twin.shared.system_gateway.policy import (
        PolicyContext,
        PolicyReason,
        evaluate_action_policy,
    )
    from twin.shared.system_gateway.audit import (
        AuditOutcome,
        EVENT_ACTION_COMPLETED,
        EVENT_ACTION_DENIED,
        EVENT_ACTION_FAILED,
        EVENT_ACTION_STARTED,
        EVENT_ACTION_TIMED_OUT,
        EVENT_APPROVAL_RESOLVED,
        audit_event,
    )
    from twin.shared.system_gateway.auth import verify_approval_token

    state = _state(request)
    actor = request.get("auth_actor", "unknown")
    try:
        payload = await _read_json(request)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    action = str(payload.get("action") or "").strip()
    arguments = payload.get("arguments") or {}
    approval_id = payload.get("approval_id")
    timeout = _coerce_timeout(payload.get("timeout"))
    max_output_chars = _coerce_max_output(payload.get("max_output_chars"))

    adapter = select_adapter()
    caps = adapter.capabilities().to_dict()
    caps["service"] = "system_gateway"
    structured_actions = set(caps.get("structured_actions") or [])
    action_available = action in structured_actions

    decision = evaluate_action_policy(
        action=action,
        action_available=action_available,
        context=PolicyContext(
            actor=actor,
            action=action,
            is_raw_shell=False,
            approval_id=approval_id,
            capabilities=caps,
        ),
        consumed_approvals=state.consumed_approvals,
    )

    if decision.verdict.value == "deny":
        return _deny_action(
            state, actor, action, approval_id, decision.reason.value, timeout
        )

    # Approval authenticity: the token must be a valid, action-bound,
    # actor-bound, unexpired signature — bare presence is not enough.
    token_result = verify_approval_token(
        secret=state.shared_secret,
        token=approval_id,
        action=action,
        actor=actor,
    )
    if not token_result.valid:
        return _deny_action(
            state,
            actor,
            action,
            approval_id,
            PolicyReason.APPROVAL_INVALID.value,
            timeout,
        )

    # Single-use: the token's nonce is the replay key. consume IS the check.
    if not state.consume_approval(token_result.nonce):
        return _deny_action(
            state,
            actor,
            action,
            approval_id,
            PolicyReason.APPROVAL_REPLAYED.value,
            timeout,
        )

    state.record_audit(
        audit_event(
            EVENT_APPROVAL_RESOLVED,
            AuditOutcome.RESOLVED,
            actor=actor,
            subject=action,
            approval_id=approval_id,
            details={"nonce": token_result.nonce},
        ).to_dict()
    )
    state.record_audit(
        audit_event(
            EVENT_ACTION_STARTED,
            AuditOutcome.STARTED,
            actor=actor,
            subject=action,
            approval_id=approval_id,
            details={"timeout": timeout, "arguments": arguments},
        ).to_dict()
    )

    try:
        result = await asyncio.wait_for(
            adapter.run_action(
                action,
                dict(arguments),
                timeout=timeout,
                max_output_chars=max_output_chars,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        state.record_audit(
            audit_event(
                EVENT_ACTION_TIMED_OUT,
                AuditOutcome.TIMED_OUT,
                actor=actor,
                subject=action,
                approval_id=approval_id,
                details={"timeout": timeout},
            ).to_dict()
        )
        return web.json_response(
            {"ok": False, "error": "action_timed_out", "action": action},
            status=504,
        )

    ok = bool(result.get("ok"))
    if not ok:
        error = result.get("error") or "action_failed"
        state.record_audit(
            audit_event(
                EVENT_ACTION_FAILED,
                AuditOutcome.FAILED,
                actor=actor,
                subject=action,
                approval_id=approval_id,
                details={"error": error},
            ).to_dict()
        )
        status = 400 if error == "action_not_supported" else 500
        return web.json_response(
            {"ok": False, "error": error, "action": action}, status=status
        )

    state.record_audit(
        audit_event(
            EVENT_ACTION_COMPLETED,
            AuditOutcome.COMPLETED,
            actor=actor,
            subject=action,
            approval_id=approval_id,
            details={"exit_code": result.get("exit_code")},
        ).to_dict()
    )
    return web.json_response(
        {
            "ok": True,
            "output": result.get("output", ""),
            "error": result.get("error"),
            "exit_code": result.get("exit_code"),
            "data": result.get("data") or {},
        }
    )


def _deny_action(
    state: GatewayState,
    actor: str,
    action: str,
    approval_id: Any,
    reason: str,
    timeout: int,
) -> web.Response:
    from twin.shared.system_gateway.audit import (
        AuditOutcome,
        EVENT_ACTION_DENIED,
        audit_event,
    )

    state.record_audit(
        audit_event(
            EVENT_ACTION_DENIED,
            AuditOutcome.DENIED,
            actor=actor,
            subject=action,
            approval_id=approval_id,
            details={"reason": reason, "timeout": timeout},
        ).to_dict()
    )
    return web.json_response({"ok": False, "error": reason}, status=403)


async def run_shell(request: web.Request) -> web.Response:
    """Raw shell endpoint.

    Denied by default. When enabled by configuration it still requires a
    fresh, non-replayed approval id. Phase B does not execute the command.
    """

    from twin.shared.system_gateway.policy import (
        PolicyContext,
        PolicyReason,
        evaluate_shell_policy,
    )
    from twin.shared.system_gateway.audit import (
        AuditOutcome,
        EVENT_ACTION_DENIED,
        EVENT_ACTION_STARTED,
        EVENT_APPROVAL_RESOLVED,
        audit_event,
    )
    from twin.shared.system_gateway.auth import verify_approval_token

    state = _state(request)
    config = _config(request)
    actor = request.get("auth_actor", "unknown")
    try:
        payload = await _read_json(request)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    command = str(payload.get("command") or "").strip()
    shell = payload.get("shell")
    cwd = payload.get("cwd")
    timeout = _coerce_timeout(payload.get("timeout"))
    max_output_chars = _coerce_max_output(payload.get("max_output_chars"))
    approval_id = payload.get("approval_id")

    caps = capabilities_payload()

    def _deny_shell(reason: str) -> web.Response:
        state.record_audit(
            audit_event(
                EVENT_ACTION_DENIED,
                AuditOutcome.DENIED,
                actor=actor,
                subject="shell",
                approval_id=approval_id,
                details={
                    "reason": reason,
                    "command": _truncate(command, 200),
                    "shell": shell,
                    "cwd": cwd,
                    "timeout": timeout,
                },
            ).to_dict()
        )
        return web.json_response({"ok": False, "error": reason}, status=403)

    decision = evaluate_shell_policy(
        raw_shell_enabled=config.raw_shell_enabled,
        context=PolicyContext(
            actor=actor,
            action="shell",
            is_raw_shell=True,
            approval_id=approval_id,
            capabilities=caps,
        ),
        consumed_approvals=state.consumed_approvals,
    )

    if decision.verdict.value == "deny":
        return _deny_shell(decision.reason.value)

    # Raw shell binds its approval token to the canonical action "shell".
    token_result = verify_approval_token(
        secret=state.shared_secret,
        token=approval_id,
        action="shell",
        actor=actor,
    )
    if not token_result.valid:
        return _deny_shell(PolicyReason.APPROVAL_INVALID.value)

    if not state.consume_approval(token_result.nonce):
        return _deny_shell(PolicyReason.APPROVAL_REPLAYED.value)

    state.record_audit(
        audit_event(
            EVENT_APPROVAL_RESOLVED,
            AuditOutcome.RESOLVED,
            actor=actor,
            subject="shell",
            approval_id=approval_id,
            details={"nonce": token_result.nonce},
        ).to_dict()
    )
    state.record_audit(
        audit_event(
            EVENT_ACTION_STARTED,
            AuditOutcome.STARTED,
            actor=actor,
            subject="shell",
            approval_id=approval_id,
            details={
                "command": _truncate(command, 200),
                "shell": shell,
                "cwd": cwd,
                "timeout": timeout,
                "max_output_chars": max_output_chars,
            },
        ).to_dict()
    )

    # Phase 1 does not execute raw shell; raw_shell is disabled by default and
    # the gate above only passes when explicitly enabled in config.
    return web.json_response(
        {
            "ok": False,
            "error": "shell_execution_not_implemented",
            "timeout": timeout,
        },
        status=501,
    )


async def self_update(request: web.Request) -> web.Response:
    """Restricted endpoint for an in-place update request.

    The service does not automatically download or restart itself. It validates
    the owner-issued approval token, records the request, and returns a queued
    status. The actual update must be performed by the host package manager or
    admin (see ``system-gateway install`` / ``system-gateway uninstall``).
    """

    from twin.shared.system_gateway.auth import verify_approval_token
    from twin.shared.system_gateway.audit import (
        AuditOutcome,
        EVENT_ACTION_DENIED,
        EVENT_APPROVAL_RESOLVED,
        EVENT_ACTION_STARTED,
        audit_event,
    )
    from twin.shared.system_gateway.policy import (
        PolicyContext,
        PolicyReason,
        evaluate_action_policy,
    )

    state = _state(request)
    actor = request.get("auth_actor", "unknown")
    try:
        payload = await _read_json(request)
    except ValueError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    from_version = str(payload.get("from_version") or "").strip()
    target_version = str(payload.get("to_version") or "").strip() or None
    approval_id = payload.get("approval_id")
    caps = capabilities_payload()

    decision = evaluate_action_policy(
        action="self.update",
        action_available=True,
        context=PolicyContext(
            actor=actor,
            action="self.update",
            is_raw_shell=False,
            approval_id=approval_id,
            capabilities=caps,
        ),
        consumed_approvals=state.consumed_approvals,
    )
    if decision.verdict.value == "deny":
        return _deny_action(
            state,
            actor,
            "self.update",
            approval_id,
            decision.reason.value,
            30,
        )

    token_result = verify_approval_token(
        secret=state.shared_secret,
        token=approval_id,
        action="self.update",
        actor=actor,
    )
    if not token_result.valid:
        return _deny_action(
            state,
            actor,
            "self.update",
            approval_id,
            PolicyReason.APPROVAL_INVALID.value,
            30,
        )

    if not state.consume_approval(token_result.nonce):
        return _deny_action(
            state,
            actor,
            "self.update",
            approval_id,
            PolicyReason.APPROVAL_REPLAYED.value,
            30,
        )

    if from_version != SERVICE_VERSION:
        return web.json_response(
            {
                "ok": False,
                "error": "version_mismatch",
                "message": f"service is {SERVICE_VERSION}, request claimed {from_version}",
            },
            status=409,
        )

    state.record_audit(
        audit_event(
            EVENT_APPROVAL_RESOLVED,
            AuditOutcome.RESOLVED,
            actor=actor,
            subject="self.update",
            approval_id=approval_id,
            details={"nonce": token_result.nonce},
        ).to_dict()
    )
    state.record_audit(
        audit_event(
            EVENT_ACTION_STARTED,
            AuditOutcome.STARTED,
            actor=actor,
            subject="self.update",
            approval_id=approval_id,
            details={
                "from_version": from_version,
                "target_version": target_version,
            },
        ).to_dict()
    )

    # Do not auto-download or restart. The admin must run the package update
    # and restart the service out-of-band.
    message = (
        f"update accepted for {SERVICE_VERSION}"
        + (f" -> {target_version}" if target_version else "")
        + ". Run the package update and restart the service to apply."
    )
    return web.json_response({"ok": True, "message": message})


def create_app(config: GatewayConfig | None = None) -> web.Application:
    """Create the aiohttp application."""

    resolved = config or GatewayConfig.from_env()
    app = web.Application(middlewares=[auth_middleware])
    app[CONFIG_KEY] = resolved
    app[STATE_KEY] = GatewayState(
        raw_shell_enabled=resolved.raw_shell_enabled,
        shared_secret=resolved.shared_secret,
    )
    app.router.add_get("/health", health)
    app.router.add_get("/capabilities", capabilities)
    app.router.add_post("/actions/run", run_action)
    app.router.add_post("/shell/run", run_shell)
    app.router.add_post("/self/update", self_update)
    return app


async def _read_json(request: web.Request) -> dict[str, Any]:
    raw = await request.read()
    if not raw:
        return {}
    try:
        data = jsonlib.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid JSON body: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data


def _extract_headers(request: web.Request) -> dict[str, str]:
    return {key: value for key, value in request.headers.items()}


def _coerce_timeout(value: Any) -> int:
    try:
        if value is None:
            return 30
        seconds = int(value)
    except (TypeError, ValueError):
        return 30
    return max(1, min(seconds, 300))


def _coerce_max_output(value: Any) -> int:
    try:
        if value is None:
            return 8000
        chars = int(value)
    except (TypeError, ValueError):
        return 8000
    return max(256, min(chars, 1_000_000))


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... [+{len(text) - max_chars} chars]"


# Module-level aliases so middleware tests can call the handler bodies without
# registering routes.
actions_route = run_action
shell_route = run_shell

