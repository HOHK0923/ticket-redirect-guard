"""Session state tracking in Redis for the queue system."""

from __future__ import annotations

import time

import redis.asyncio as redis

from guard.config import get_settings


def _key(session_id: str, suffix: str) -> str:
    return f"guard:session:{session_id}:{suffix}"


async def mark_quiz_passed(r: redis.Redis, session_id: str) -> None:
    cfg = get_settings()
    await r.setex(_key(session_id, "quiz_passed"), cfg.session_ttl_seconds, "1")


async def is_quiz_passed(r: redis.Redis, session_id: str) -> bool:
    return await r.exists(_key(session_id, "quiz_passed")) > 0


async def set_queue_entered(r: redis.Redis, session_id: str) -> None:
    cfg = get_settings()
    ts = int(time.time())
    await r.setex(_key(session_id, "queue_entered"), cfg.session_ttl_seconds, str(ts))


async def get_queue_entered_time(r: redis.Redis, session_id: str) -> int | None:
    val = await r.get(_key(session_id, "queue_entered"))
    return int(val) if val else None
