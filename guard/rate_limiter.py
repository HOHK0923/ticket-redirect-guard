"""Sliding-window rate counter backed by Redis sorted sets."""

from __future__ import annotations

import time

import redis.asyncio as redis

from guard.config import get_settings


async def record_and_count(
    r: redis.Redis, ip: str, now: float | None = None
) -> tuple[int, int]:
    """Record a hit for `ip` and return (short_count, long_count).

    Uses a single Redis pipeline (1 round-trip) for all operations.
    """
    cfg = get_settings()
    now = now or time.time()
    member = f"{now}"

    key_short = f"rate:{ip}:short"
    key_long = f"rate:{ip}:long"

    short_cutoff = now - cfg.rate_window_short
    long_cutoff = now - cfg.rate_window_long

    pipe = r.pipeline(transaction=False)
    # Add to both sets
    pipe.zadd(key_short, {member: now})
    pipe.zadd(key_long, {member: now})
    # Remove expired entries
    pipe.zremrangebyscore(key_short, "-inf", short_cutoff)
    pipe.zremrangebyscore(key_long, "-inf", long_cutoff)
    # Count remaining
    pipe.zcard(key_short)
    pipe.zcard(key_long)
    # Set TTLs
    pipe.expire(key_short, cfg.rate_window_short + 5)
    pipe.expire(key_long, cfg.rate_window_long + 5)

    results = await pipe.execute()
    short_count = results[4]
    long_count = results[5]

    return short_count, long_count
