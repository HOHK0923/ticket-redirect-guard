"""HMAC-signed challenge token utilities."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import redis.asyncio as redis

from app.config import get_settings


def _sign(payload: str) -> str:
    secret = get_settings().hmac_secret.encode()
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def create_token(ip: str, user_agent: str) -> tuple[str, str]:
    """Create a signed challenge token.

    Returns (token_b64, jti).
    """
    cfg = get_settings()
    jti = uuid.uuid4().hex
    payload = {
        "ip_ua": hashlib.sha256(f"{ip}|{user_agent}".encode()).hexdigest()[:16],
        "exp": int(time.time()) + cfg.token_ttl_seconds,
        "jti": jti,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = _sign(raw)
    token = f"{raw}|{sig}"
    return token, jti


def verify_token(token: str, ip: str, user_agent: str) -> tuple[bool, str | None, str]:
    """Verify token signature, expiry, and IP+UA binding.

    Returns (valid, jti, reason).
    """
    parts = token.rsplit("|", 1)
    if len(parts) != 2:
        return False, None, "malformed"

    raw, sig = parts
    expected_sig = _sign(raw)
    if not hmac.compare_digest(sig, expected_sig):
        return False, None, "bad_signature"

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, None, "bad_json"

    if payload.get("exp", 0) < int(time.time()):
        return False, None, "expired"

    expected_hash = hashlib.sha256(f"{ip}|{user_agent}".encode()).hexdigest()[:16]
    if payload.get("ip_ua") != expected_hash:
        return False, None, "ip_ua_mismatch"

    return True, payload.get("jti"), "ok"


async def is_jti_used(r: redis.Redis, jti: str) -> bool:
    return await r.exists(f"jti:{jti}") > 0


async def mark_jti_used(r: redis.Redis, jti: str) -> None:
    cfg = get_settings()
    await r.setex(f"jti:{jti}", cfg.token_ttl_seconds + 10, "1")
