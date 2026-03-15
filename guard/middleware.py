"""Traffic guard middleware — session-based behavioral analysis.

Sits on the security proxy server. Intercepts all requests,
tracks per-session behavior in Redis, computes AI features,
and blocks suspicious sessions via 302 redirect.

Flow: AI Quiz (other team) → Queue (this) → 302 redirect → Seat selection
"""

from __future__ import annotations

import collections
import json
import time
import uuid as uuid_mod
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from guard.config import get_settings
from guard.logging_config import setup_logging
from guard.metrics import metrics
from guard.models import DomainEventLog, SessionRequestRecord, ServerRequestLog
from guard.redis_client import get_redis
from guard.request_parser import (
    extract_device_id,
    extract_session_id,
    extract_session_ticket,
    extract_show_schedule_id,
    extract_target_key,
    extract_user_id,
    map_to_domain_event,
    normalize_endpoint,
)
from guard.scorer import calculate_risk_score
from guard.session_tracker import record_and_get_history

logger = setup_logging()

# Internal log buffer (ops only)
guard_log: collections.deque[dict] = collections.deque(maxlen=500)


class GuardMiddleware(BaseHTTPMiddleware):
    """Session-based traffic guard with AI feature scoring.

    Args:
        bypass_paths: Set of paths that skip the guard entirely.
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

        # --- Bypass checks ---
        if cfg.is_ip_whitelisted(client_ip):
            return await call_next(request)
        if path in cfg.get_whitelist_paths() or path in self._bypass:
            return await call_next(request)
        wl_uas = cfg.get_whitelist_uas()
        if wl_uas and any(ua in user_agent for ua in wl_uas):
            return await call_next(request)

        # --- Check if this is a sensitive (guarded) endpoint ---
        sensitive = cfg.get_sensitive_paths()
        is_sensitive = any(path.startswith(sp) for sp in sensitive)

        if not is_sensitive:
            # Non-sensitive paths pass through without scoring
            return await call_next(request)

        # --- Extract session & request data ---
        session_id = extract_session_id(request)
        normalized = normalize_endpoint(path)
        ts_ms = int(time.time() * 1000)

        # Parse body for target key extraction (POST requests)
        body_dict = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body_dict = json.loads(body_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        target_key = extract_target_key(path, body_dict)

        # Build session request record
        record = SessionRequestRecord(
            endpoint=normalized,
            ts_ms=ts_ms,
            target_key=target_key,
        )

        # --- Record to Redis & get history (single pipeline) ---
        r = await get_redis()
        history = await record_and_get_history(r, session_id, record)

        # --- Compute risk score ---
        result = calculate_risk_score(
            history=history,
            current_endpoint=normalized,
            current_target_key=target_key,
        )

        score = result.score
        action = "pass"

        if score >= cfg.score_high:
            action = "redirect"
            metrics.record_redirect()
            _log_decision(path, client_ip, session_id, score, action, result.reasons, result.features)
            return RedirectResponse(url=cfg.redirect_url, status_code=302)

        # --- Pass through: proxy to backend ---
        metrics.record_pass()
        start = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start) * 1000)

        # --- Emit structured logs ---
        _log_decision(path, client_ip, session_id, score, action, result.reasons, result.features)

        # Server request log
        request_log = ServerRequestLog(
            session_id=session_id,
            user_id=extract_user_id(request),
            session_ticket=extract_session_ticket(request),
            endpoint=normalized,
            ts_ms_server=ts_ms,
            status=response.status_code,
            latency_ms=latency_ms,
            ip=client_ip,
            device_id=extract_device_id(request),
            request_id=uuid_mod.uuid4().hex[:16],
            show_schedule_id=extract_show_schedule_id(path),
            order_id=body_dict.get("orderId") if body_dict else None,
            seat_ids=body_dict.get("seatIds", []) if body_dict else [],
        )
        logger.info("server_request_log", extra={"server_request_log": request_log.to_dict()})

        # Domain event log
        event_name = map_to_domain_event(path, request.method, response.status_code)
        if event_name:
            event = DomainEventLog(
                event_name=event_name,
                ts_ms=ts_ms,
                session_id=session_id,
            )
            logger.info("domain_event_log", extra={"domain_event": event.to_dict()})

        return response


def _log_decision(
    path: str, ip: str, session_id: str,
    score: int, action: str, reasons: list[str], features: dict,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "path": path,
        "ip": ip,
        "session_id": session_id[:12] + "..." if len(session_id) > 12 else session_id,
        "score": score,
        "action": action,
        "features": features,
        "reason": ",".join(reasons) if reasons else "none",
    }
    guard_log.append(entry)
    logger.info("guard_decision", extra={"guard": entry})
