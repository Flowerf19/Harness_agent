"""Unit tests for System Gateway HMAC signing and replay protection."""
from __future__ import annotations

import time

import pytest

from twin.shared.system_gateway.auth import (
    NonceStore,
    approval_replay_protection,
    canonical_message,
    extract_auth_headers,
    headers_from_signed,
    is_timestamp_within_skew,
    mint_approval_token,
    sign_request,
    verify_approval_token,
    verify_signature,
)


SECRET = "super-secret-shared-key"
OTHER_SECRET = "different-secret"


def test_signature_round_trip_succeeds_with_same_secret():
    signed = sign_request(
        secret=SECRET,
        method="POST",
        path="/actions/run",
        actor="march7",
        body=b'{"action":"system.status"}',
    )
    headers = headers_from_signed(signed)

    assert verify_signature(
        SECRET,
        method="POST",
        path="/actions/run",
        timestamp=signed.timestamp,
        nonce=signed.nonce,
        actor=signed.actor,
        body=b'{"action":"system.status"}',
        signature=headers["X-System-Gateway-Signature"],
    )


def test_signature_fails_with_different_secret():
    signed = sign_request(
        secret=SECRET,
        method="POST",
        path="/actions/run",
        actor="march7",
        body=b"{}",
    )

    assert not verify_signature(
        OTHER_SECRET,
        method="POST",
        path="/actions/run",
        timestamp=signed.timestamp,
        nonce=signed.nonce,
        actor=signed.actor,
        body=b"{}",
        signature=signed.signature,
    )


def test_signature_fails_when_body_changes():
    signed = sign_request(
        secret=SECRET,
        method="POST",
        path="/actions/run",
        actor="march7",
        body=b'{"action":"system.status"}',
    )

    assert not verify_signature(
        SECRET,
        method="POST",
        path="/actions/run",
        timestamp=signed.timestamp,
        nonce=signed.nonce,
        actor=signed.actor,
        body=b'{"action":"system.disk_usage"}',
        signature=signed.signature,
    )


def test_signature_fails_when_path_changes():
    signed = sign_request(
        secret=SECRET,
        method="POST",
        path="/actions/run",
        actor="march7",
        body=b"{}",
    )

    assert not verify_signature(
        SECRET,
        method="POST",
        path="/shell/run",
        timestamp=signed.timestamp,
        nonce=signed.nonce,
        actor=signed.actor,
        body=b"{}",
        signature=signed.signature,
    )


def test_signature_fails_when_secret_is_missing():
    signed = sign_request(
        secret=SECRET,
        method="POST",
        path="/actions/run",
        actor="march7",
        body=b"{}",
    )

    assert not verify_signature(
        None,
        method="POST",
        path="/actions/run",
        timestamp=signed.timestamp,
        nonce=signed.nonce,
        actor=signed.actor,
        body=b"{}",
        signature=signed.signature,
    )


def test_canonical_message_binds_body_hash():
    msg_a = canonical_message(
        method="POST",
        path="/x",
        timestamp="1",
        nonce="n",
        actor="a",
        body=b"hello",
    )
    msg_b = canonical_message(
        method="POST",
        path="/x",
        timestamp="1",
        nonce="n",
        actor="a",
        body=b"hellp",
    )

    assert msg_a != msg_b


def test_extract_auth_headers_is_case_insensitive():
    headers = {
        "x-system-gateway-signature": "sig",
        "X-System-Gateway-Timestamp": "1700000000",
        "X-SYSTEM-GATEWAY-NONCE": "n",
        "x-system-gateway-actor": "march7",
    }

    extracted = extract_auth_headers(headers)

    assert extracted == {
        "signature": "sig",
        "timestamp": "1700000000",
        "nonce": "n",
        "actor": "march7",
    }


def test_is_timestamp_within_skew_accepts_recent_timestamp():
    now = 1_700_000_000.0
    assert is_timestamp_within_skew(str(int(now)), now=now)


def test_is_timestamp_within_skew_rejects_stale_timestamp():
    now = 1_700_000_000.0
    stale = now - 3600  # one hour old
    assert not is_timestamp_within_skew(str(int(stale)), now=now)


def test_is_timestamp_within_skew_rejects_non_integer():
    assert not is_timestamp_within_skew("not-a-number")


def test_nonce_store_marks_nonce_as_seen():
    store = NonceStore()

    assert store.is_fresh("abc")
    assert not store.is_fresh("abc")


def test_nonce_store_evicts_old_entries(monkeypatch):
    store = NonceStore(ttl_seconds=10)

    base = 1_700_000_000.0
    assert store.is_fresh("old", now=base)
    # Advance virtual time past TTL and verify old nonce can be reused.
    assert store.is_fresh("new", now=base + 11)
    # 'old' should have been evicted by now.
    assert store.is_fresh("old", now=base + 11)


def test_approval_replay_protection_rejects_blank_and_consumed():
    consumed = {"a"}

    assert not approval_replay_protection(consumed, None)
    assert not approval_replay_protection(consumed, "")
    assert not approval_replay_protection(consumed, "a")
    assert approval_replay_protection(consumed, "b")


def test_sign_request_assigns_timestamp_and_nonce_when_missing(monkeypatch):
    fixed = 1_700_000_123
    monkeypatch.setattr("twin.shared.system_gateway.auth.time.time", lambda: float(fixed))

    signed = sign_request(
        secret=SECRET,
        method="POST",
        path="/actions/run",
        actor="march7",
        body=b"{}",
    )

    assert signed.timestamp == str(fixed)
    assert signed.nonce
    assert signed.signature


# --- Action-bound approval tokens -------------------------------------------


def test_approval_token_round_trip_is_valid():
    token = mint_approval_token(secret=SECRET, action="system.status", actor="march7")
    result = verify_approval_token(
        secret=SECRET, token=token, action="system.status", actor="march7"
    )

    assert result.valid is True
    assert result.reason == "approved"
    assert result.nonce


def test_approval_token_rejects_forged_signature():
    token = mint_approval_token(secret=SECRET, action="system.status", actor="march7")
    result = verify_approval_token(
        secret=OTHER_SECRET, token=token, action="system.status", actor="march7"
    )

    assert result.valid is False
    assert result.reason == "approval_signature_mismatch"


def test_approval_token_rejects_action_mismatch():
    token = mint_approval_token(secret=SECRET, action="system.status", actor="march7")
    result = verify_approval_token(
        secret=SECRET, token=token, action="docker.list_containers", actor="march7"
    )

    assert result.valid is False
    assert result.reason == "approval_action_mismatch"


def test_approval_token_rejects_actor_mismatch():
    token = mint_approval_token(secret=SECRET, action="system.status", actor="march7")
    result = verify_approval_token(
        secret=SECRET, token=token, action="system.status", actor="evernight"
    )

    assert result.valid is False
    assert result.reason == "approval_actor_mismatch"


def test_approval_token_rejects_expired():
    base = 1_700_000_000.0
    token = mint_approval_token(
        secret=SECRET, action="system.status", actor="march7", ttl_seconds=120, now=base
    )
    result = verify_approval_token(
        secret=SECRET,
        token=token,
        action="system.status",
        actor="march7",
        now=base + 1000,
    )

    assert result.valid is False
    assert result.reason == "approval_expired"


def test_approval_token_rejects_malformed():
    for bad in (None, "", "not-a-token", "no.dot.here.x"):
        result = verify_approval_token(
            secret=SECRET, token=bad, action="system.status", actor="march7"
        )
        assert result.valid is False


def test_approval_token_nonce_is_unique_per_mint():
    a = mint_approval_token(secret=SECRET, action="system.status", actor="march7")
    b = mint_approval_token(secret=SECRET, action="system.status", actor="march7")

    assert a != b
