"""Guard middleware — intercepts requests and applies risk-based actions."""

from __future__ import annotations

import asyncio
import random
import time
from urllib.parse import quote, urlencode

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.config import get_settings
from app.logging_config import setup_logging
from app.metrics import metrics
from app.rate_limiter import record_and_count
from app.redis_client import get_redis
from app.scorer import calculate_risk_score

logger = setup_logging()

CHALLENGE_COOKIE = "trg_token"


class GuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        cfg = get_settings()

        # --- Kill switch ---
        if not cfg.guard_enabled:
            return await call_next(request)

        path = request.url.path
        client_ip = request.client.host if request.client else "0.0.0.0"
        user_agent = request.headers.get("user-agent", "")

        # --- Whitelist checks ---
        if cfg.is_ip_whitelisted(client_ip):
            return await call_next(request)

        if path in cfg.get_whitelist_paths():
            return await call_next(request)

        wl_uas = cfg.get_whitelist_uas()
        if wl_uas and any(ua in user_agent for ua in wl_uas):
            return await call_next(request)

        # Internal endpoints bypass
        if path in ("/challenge", "/challenge/verify"):
            return await call_next(request)

        # --- Rate counting ---
        r = await get_redis()
        short_count, long_count = await record_and_count(r, client_ip)

        # --- Risk scoring ---
        has_cookie = CHALLENGE_COOKIE in request.cookies
        has_session = "session_id" in request.cookies
        accept_language = request.headers.get("accept-language", "")

        result = calculate_risk_score(
            short_count=short_count,
            long_count=long_count,
            has_cookie=has_cookie,
            has_session=has_session,
            user_agent=user_agent,
            accept_language=accept_language,
            path=path,
        )

        score = result.score
        action = "pass"
        delay_ms = 0

        if score >= cfg.score_high:
            # HIGH — redirect to challenge
            action = "redirect"
            metrics.record_redirect()
            _log(path, client_ip, score, action, 0, result.reasons)
            return _redirect_to_challenge(path)

        if score >= cfg.score_mid:
            # MID — random delay or redirect
            if random.random() < 0.4:
                action = "redirect"
                metrics.record_redirect()
                _log(path, client_ip, score, action, 0, result.reasons)
                return _redirect_to_challenge(path)
            else:
                delay_ms = random.randint(cfg.delay_min_ms, cfg.delay_max_ms)
                action = "delay"
                await asyncio.sleep(delay_ms / 1000.0)
                metrics.record_delay(delay_ms)

        # LOW or delayed-pass
        if action == "pass":
            metrics.record_pass()

        _log(path, client_ip, score, action, delay_ms, result.reasons)
        return await call_next(request)


def _redirect_to_challenge(return_to: str) -> RedirectResponse:
    qs = urlencode({"return_to": return_to})
    return RedirectResponse(
        url=f"/challenge?{qs}",
        status_code=302,
    )


def _log(
    path: str,
    ip: str,
    score: int,
    action: str,
    delay_ms: int,
    reasons: list[str],
) -> None:
    logger.info(
        "guard_decision",
        extra={
            "guard": {
                "path": path,
                "ip": ip,
                "score": score,
                "action": action,
                "delay_ms": delay_ms,
                "reason": ",".join(reasons) if reasons else "none",
            }
        },
    )
