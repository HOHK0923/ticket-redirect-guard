"""Session-based request tracking backed by Redis sorted sets.

Stores request history needed to compute the 3 AI features.
All Redis operations are pipelined for minimal round-trips.
"""

from __future__ import annotations

import time

import redis.asyncio as redis

from guard.config import get_settings
from guard.models import SessionRequestRecord

# Delimiter for compact serialization (faster than JSON)
_SEP = "|"


def _session_key(session_id: str, suffix: str = "requests") -> str:
    return f"session:{session_id}:{suffix}"


def _serialize(record: SessionRequestRecord) -> str:
    return f"{record.endpoint}{_SEP}{record.ts_ms}{_SEP}{record.target_key}"


def _deserialize(raw: str) -> SessionRequestRecord | None:
    parts = raw.split(_SEP, 2)
    if len(parts) != 3:
        return None
    try:
        return SessionRequestRecord(
            endpoint=parts[0],
            ts_ms=int(parts[1]),
            target_key=parts[2],
        )
    except (ValueError, IndexError):
        return None


async def get_history(r: redis.Redis, session_id: str) -> list[SessionRequestRecord]:
    """Read-only fetch of session history (no new record added)."""
    key = _session_key(session_id)
    members = await r.zrange(key, 0, -1)
    records = []
    for raw in members:
        rec = _deserialize(raw)
        if rec:
            records.append(rec)
    return records


async def record_and_get_history(
    r: redis.Redis,
    session_id: str,
    record: SessionRequestRecord,
) -> list[SessionRequestRecord]:
    """Record a request and return session history in a single pipeline (1 round-trip)."""
    cfg = get_settings()
    key = _session_key(session_id)
    ttl = cfg.session_idle_timeout_seconds

    member = _serialize(record)
    cutoff = record.ts_ms - (ttl * 1000)

    pipe = r.pipeline(transaction=False)
    pipe.zadd(key, {member: record.ts_ms})
    pipe.zremrangebyscore(key, "-inf", cutoff)  # Prune old entries
    pipe.zrange(key, 0, -1)
    pipe.expire(key, ttl)
    results = await pipe.execute()

    members = results[2]  # ZRANGE result
    records = []
    for raw in members:
        rec = _deserialize(raw)
        if rec:
            records.append(rec)
    return records


async def mark_quiz_passed(r: redis.Redis, session_id: str) -> None:
    cfg = get_settings()
    await r.setex(_session_key(session_id, "quiz_passed"), cfg.session_idle_timeout_seconds, "1")


async def is_quiz_passed(r: redis.Redis, session_id: str) -> bool:
    return await r.exists(_session_key(session_id, "quiz_passed")) > 0


async def set_queue_entered(r: redis.Redis, session_id: str) -> None:
    cfg = get_settings()
    ts = int(time.time())
    await r.setex(_session_key(session_id, "queue_entered"), cfg.session_idle_timeout_seconds + 30, str(ts))


async def get_queue_entered_time(r: redis.Redis, session_id: str) -> int | None:
    val = await r.get(_session_key(session_id, "queue_entered"))
    return int(val) if val else None
