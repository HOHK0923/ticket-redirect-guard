"""Sliding-window rate counter backed by Redis sorted sets."""

from __future__ import annotations

import time

import redis.asyncio as redis

from app.config import get_settings


async def _count_in_window(r: redis.Redis, key: str, window: int, now: float) -> int:
    """Return request count in the last `window` seconds for `key`."""
    cutoff = now - window
    # Remove expired entries
    await r.zremrangebyscore(key, "-inf", cutoff)
    return await r.zcard(key)


async def record_and_count(
    r: redis.Redis, ip: str, now: float | None = None
) -> tuple[int, int]:
    """Record a hit for `ip` and return (short_count, long_count).

    Two sorted sets per IP:
      rate:{ip}:short  — short window (e.g. 10 s)
      rate:{ip}:long   — long window  (e.g. 60 s)
    Score = timestamp, member = unique timestamp string to allow duplicates.
    """
    cfg = get_settings()
    now = now or time.time()
    member = f"{now}"

    key_short = f"rate:{ip}:short"
    key_long = f"rate:{ip}:long"

    pipe = r.pipeline(transaction=False)
    pipe.zadd(key_short, {member: now})
    pipe.expire(key_short, cfg.rate_window_short + 5)
    pipe.zadd(key_long, {member: now})
    pipe.expire(key_long, cfg.rate_window_long + 5)
    await pipe.execute()

    short_count = await _count_in_window(r, key_short, cfg.rate_window_short, now)
    long_count = await _count_in_window(r, key_long, cfg.rate_window_long, now)
    return short_count, long_count
