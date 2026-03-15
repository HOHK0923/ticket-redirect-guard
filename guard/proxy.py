"""Reverse proxy that forwards clean traffic to the upstream backend.

All requests pass through GuardMiddleware first.
Blocked requests get 302-redirected before reaching the backend.
Clean requests are proxied transparently to UPSTREAM_URL.
"""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import Response

from guard.config import get_settings

# Persistent async client (connection pooling)
_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(follow_redirects=False, timeout=30.0)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# Headers that should not be forwarded
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "content-length", "host",
})


async def proxy_request(request: Request) -> Response:
    """Forward the request to the upstream backend and stream the response back."""
    cfg = get_settings()
    client = await get_client()

    # Build upstream URL
    upstream = cfg.upstream_url.rstrip("/")
    url = f"{upstream}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    # Forward headers (skip hop-by-hop)
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP
    }
    # Pass original client IP to backend
    client_ip = request.client.host if request.client else "0.0.0.0"
    headers["x-forwarded-for"] = client_ip
    headers["x-real-ip"] = client_ip

    # Read request body
    body = await request.body()

    # Forward to upstream
    upstream_resp = await client.request(
        method=request.method,
        url=url,
        headers=headers,
        content=body if body else None,
    )

    # Build response headers (skip hop-by-hop)
    resp_headers = {
        k: v for k, v in upstream_resp.headers.items()
        if k.lower() not in HOP_BY_HOP
    }

    return Response(
        content=upstream_resp.content,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
    )
