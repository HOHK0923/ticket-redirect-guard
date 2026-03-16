"""Queue gate middleware — enforces queue pass before backend access.

Every user must pass through the queue before accessing ticketing APIs.
No queue pass token → 302 redirect to queue page.
This prevents queue jumping (새치기 방지).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from guard.config import get_settings
from guard.queue_token import verify_queue_pass
from guard.redis_client import get_redis


class GuardMiddleware(BaseHTTPMiddleware):
    """Checks queue pass token on sensitive endpoints.

    No token → 302 redirect to queue.
    """

    def __init__(self, app, bypass_paths: set[str] | None = None):
        super().__init__(app)
        self._bypass = bypass_paths or set()

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        cfg = get_settings()

        if not cfg.guard_enabled:
            return await call_next(request)

        path = request.url.path

        # Internal/ops paths skip check
        if path in self._bypass:
            return await call_next(request)

        # Only guard sensitive endpoints
        sensitive = cfg.get_sensitive_paths()
        if not any(path.startswith(sp) for sp in sensitive):
            return await call_next(request)

        # --- Queue pass check (새치기 방지) ---
        session_id = (
            request.headers.get("uuid")
            or request.headers.get("x-session-id")
            or request.cookies.get("guard_session")
        )

        if not session_id:
            return RedirectResponse(url="/_guard/queue", status_code=302)

        r = await get_redis()
        if not await verify_queue_pass(r, session_id):
            # No queue pass → must go through queue first
            return RedirectResponse(url="/_guard/queue", status_code=302)

        # Has valid queue pass → allow through to backend
        return await call_next(request)
