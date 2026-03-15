"""Traffic guard middleware.

Drop-in middleware for any FastAPI/Starlette application.
Detects suspicious traffic via rate + behavioral scoring,
then silently 302-redirects bots to a configured URL.
Normal users are never affected.

Usage:
    from guard import GuardMiddleware

    app = FastAPI()
    app.add_middleware(
        GuardMiddleware,
        bypass_paths={"/", "/about", "/login"},
    )
"""

from __future__ import annotations

import asyncio
import collections
import random
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from guard.config import get_settings
from guard.logging_config import setup_logging
from guard.metrics import metrics
from guard.rate_limiter import record_and_count
from guard.redis_client import get_redis
from guard.scorer import calculate_risk_score

logger = setup_logging()

COOKIE_NAME = "sid"

# Internal log buffer (ops only)
guard_log: collections.deque[dict] = collections.deque(maxlen=500)


class GuardMiddleware(BaseHTTPMiddleware):
    """Plug-and-play traffic guard.

    Args:
        bypass_paths: Set of paths that skip the guard entirely (pages, static, etc.)
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
        client_ip = request.client.host if request.client else "0.0.0.0"
        user_agent = request.headers.get("user-agent", "")

        # Bypass
        if cfg.is_ip_whitelisted(client_ip):
            return await call_next(request)
        if path in cfg.get_whitelist_paths():
            return await call_next(request)
        if path in self._bypass:
            return await call_next(request)
        wl_uas = cfg.get_whitelist_uas()
        if wl_uas and any(ua in user_agent for ua in wl_uas):
            return await call_next(request)

        # Rate counting
        r = await get_redis()
        short_count, long_count = await record_and_count(r, client_ip)

        # Risk scoring
        result = calculate_risk_score(
            short_count=short_count,
            long_count=long_count,
            has_cookie=COOKIE_NAME in request.cookies,
            has_session="session_id" in request.cookies,
            user_agent=user_agent,
            accept_language=request.headers.get("accept-language", ""),
            path=path,
        )

        score = result.score
        action = "pass"
        delay_ms = 0

        if score >= cfg.score_high:
            action = "redirect"
            metrics.record_redirect()
            _log(path, client_ip, score, action, 0, result.reasons)
            return RedirectResponse(url=cfg.redirect_url, status_code=302)

        if score >= cfg.score_mid:
            if random.random() < 0.4:
                action = "redirect"
                metrics.record_redirect()
                _log(path, client_ip, score, action, 0, result.reasons)
                return RedirectResponse(url=cfg.redirect_url, status_code=302)
            else:
                delay_ms = random.randint(cfg.delay_min_ms, cfg.delay_max_ms)
                action = "delay"
                await asyncio.sleep(delay_ms / 1000.0)
                metrics.record_delay(delay_ms)

        if action == "pass":
            metrics.record_pass()

        _log(path, client_ip, score, action, delay_ms, result.reasons)
        return await call_next(request)


def _log(
    path: str, ip: str, score: int, action: str, delay_ms: int, reasons: list[str],
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "path": path,
        "ip": ip,
        "score": score,
        "action": action,
        "delay_ms": delay_ms,
        "reason": ",".join(reasons) if reasons else "none",
    }
    guard_log.append(entry)
    logger.info("guard_decision", extra={"guard": entry})
