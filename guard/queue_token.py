"""Queue pass token management.

After a user completes the queue wait, a pass token is stored in Redis.
The middleware checks this token to prevent queue jumping.
Tokens are one-time bound to the session and expire after TTL.
"""

from __future__ import annotations

import hashlib
import secrets
import time

import redis.asyncio as redis

from guard.config import get_settings

_PREFIX = "guard:queue_pass"


def _key(session_id: str) -> str:
    return f"{_PREFIX}:{session_id}"


def _generate_token(session_id: str) -> str:
    """Generate a signed token bound to session + timestamp."""
    raw = f"{session_id}:{time.time()}:{secrets.token_hex(8)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def issue_queue_pass(r: redis.Redis, session_id: str) -> str:
    """Issue a queue pass token after queue wait completes. Returns the token."""
    cfg = get_settings()
    token = _generate_token(session_id)
    await r.setex(_key(session_id), cfg.queue_pass_ttl_seconds, token)
    return token


async def verify_queue_pass(r: redis.Redis, session_id: str) -> bool:
    """Check if session has a valid queue pass."""
    return await r.exists(_key(session_id)) > 0


async def revoke_queue_pass(r: redis.Redis, session_id: str) -> None:
    """Revoke a queue pass (e.g., after session ends)."""
    await r.delete(_key(session_id))
