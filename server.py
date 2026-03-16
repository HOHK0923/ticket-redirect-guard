"""Ticket Redirect Guard — queue + 302 redirect security proxy.

Architecture:
    Client → [AI Quiz] → Queue (this server) → 302 redirect → Backend

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

from guard import GuardMiddleware
from guard.config import get_settings
from guard.metrics import metrics
from guard.proxy import close_client, proxy_request
from guard.queue import handle_queue_enter, handle_queue_status
from guard.redis_client import close_redis


# --- Guard ops endpoints (/_guard/*) ---

async def health(request: Request):
    return JSONResponse({"status": "ok", "upstream": get_settings().upstream_url})


async def get_metrics(request: Request):
    return JSONResponse(metrics.snapshot())


# --- Catch-all proxy ---

async def proxy_catch_all(request: Request):
    return await proxy_request(request)


@asynccontextmanager
async def lifespan(app: Starlette):
    cfg = get_settings()
    print(f"[guard] Security proxy started")
    print(f"[guard] Upstream: {cfg.upstream_url}")
    print(f"[guard] Guard enabled: {cfg.guard_enabled}")
    print(f"[guard] Queue wait: {cfg.queue_wait_min_seconds}s min")
    print(f"[guard] Queue pass TTL: {cfg.queue_pass_ttl_seconds}s")
    yield
    await close_client()
    await close_redis()


app = Starlette(
    lifespan=lifespan,
    routes=[
        # Guard ops
        Mount("/_guard", routes=[
            Route("/health", health),
            Route("/metrics", get_metrics),
            # Queue endpoints
            Route("/queue", handle_queue_enter, methods=["GET"]),
            Route("/queue/status", handle_queue_status, methods=["GET"]),
        ]),
        # All other traffic → proxy to backend (middleware checks queue pass first)
        Route("/{path:path}", proxy_catch_all,
              methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]),
    ],
    middleware=[],
)

# Queue gate middleware — no queue pass → 302 to queue
app.add_middleware(
    GuardMiddleware,
    bypass_paths={
        "/_guard/health", "/_guard/metrics",
        "/_guard/queue", "/_guard/queue/status",
    },
)
