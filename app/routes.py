"""Application routes: challenge, metrics, health, and demo ticketing endpoints."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Cookie, Request, Response
from starlette.responses import JSONResponse, RedirectResponse

from app.config import get_settings
from app.logging_config import setup_logging
from app.metrics import metrics
from app.middleware import CHALLENGE_COOKIE
from app.redis_client import get_redis
from app.token import create_token, is_jti_used, mark_jti_used, verify_token

logger = setup_logging()
router = APIRouter()


# ──────────────────────────────────────────────
# Challenge flow
# ──────────────────────────────────────────────

@router.get("/challenge")
async def challenge_page(request: Request, return_to: str = "/"):
    """Issue a signed challenge token and set it as HttpOnly cookie.

    In a real deployment this page would render a JS challenge or
    a CAPTCHA. For this PoC we auto-issue the token immediately.
    """
    client_ip = request.client.host if request.client else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")

    token, jti = create_token(client_ip, user_agent)

    r = await get_redis()
    await mark_jti_used(r, jti)

    cfg = get_settings()
    safe_return = unquote(return_to) if return_to else "/"

    response = RedirectResponse(url=safe_return, status_code=302)
    response.set_cookie(
        key=CHALLENGE_COOKIE,
        value=token,
        httponly=True,
        max_age=cfg.token_ttl_seconds,
        samesite="lax",
        path="/",
    )

    metrics.record_challenge_pass()
    logger.info(
        "challenge_issued",
        extra={"guard": {"ip": client_ip, "return_to": safe_return}},
    )
    return response


@router.get("/challenge/verify")
async def challenge_verify(
    request: Request,
    trg_token: str | None = Cookie(default=None),
):
    """Verify an existing challenge token (diagnostic endpoint)."""
    if not trg_token:
        return JSONResponse({"valid": False, "reason": "no_token"}, status_code=401)

    client_ip = request.client.host if request.client else "0.0.0.0"
    user_agent = request.headers.get("user-agent", "")

    valid, jti, reason = verify_token(trg_token, client_ip, user_agent)
    if not valid:
        metrics.record_challenge_fail()
        return JSONResponse({"valid": False, "reason": reason}, status_code=403)

    return JSONResponse({"valid": True, "jti": jti})


# ──────────────────────────────────────────────
# Metrics / health
# ──────────────────────────────────────────────

@router.get("/metrics")
async def get_metrics():
    return JSONResponse(metrics.snapshot())


@router.get("/health")
async def health():
    return {"status": "ok"}


# ──────────────────────────────────────────────
# Demo ticketing endpoints (for testing)
# ──────────────────────────────────────────────

@router.get("/")
async def index():
    return {"message": "Ticket Redirect Guard PoC"}


@router.get("/seat")
async def seat_list():
    return {"seats": ["A1", "A2", "A3", "B1", "B2"]}


@router.get("/reserve")
async def reserve():
    return {"status": "reserved", "seat": "A1"}


@router.get("/pay")
async def pay():
    return {"status": "payment_page"}
