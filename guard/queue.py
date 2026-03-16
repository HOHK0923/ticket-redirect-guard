"""Queue (waiting page) logic.

Flow: AI Quiz passed → enter queue → wait → 302 redirect to seat selection
All users go through the queue. No scoring — just wait and redirect.
"""

from __future__ import annotations

import time

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from guard.config import get_settings
from guard.metrics import metrics
from guard.redis_client import get_redis
from guard.queue_token import issue_queue_pass
from guard.session_tracker import (
    get_queue_entered_time,
    is_quiz_passed,
    mark_quiz_passed,
    set_queue_entered,
)

QUEUE_PAGE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>대기열</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #1a1a2e;
            color: #fff;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            text-align: center;
            padding: 2rem;
        }
        .spinner {
            width: 50px; height: 50px;
            border: 4px solid rgba(255,255,255,0.2);
            border-top-color: #6c63ff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 1.5rem;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
        p { color: #aaa; font-size: 0.95rem; }
        .status { margin-top: 1rem; font-size: 0.85rem; color: #6c63ff; }
    </style>
</head>
<body>
    <div class="container">
        <div class="spinner"></div>
        <h1>잠시만 기다려주세요!</h1>
        <p>보안 확인 중입니다. 곧 좌석 선택 페이지로 이동합니다.</p>
        <div class="status" id="status">대기 중...</div>
    </div>
    <script>
        const SESSION_ID = document.cookie.split(';')
            .map(c => c.trim())
            .find(c => c.startsWith('guard_session='))
            ?.split('=')[1] || '';

        async function checkStatus() {
            try {
                const resp = await fetch('/_guard/queue/status', {
                    headers: { 'X-Session-Id': SESSION_ID }
                });
                const data = await resp.json();
                if (data.ready) {
                    document.getElementById('status').textContent = '이동 중...';
                    window.location.href = data.redirect_to;
                } else if (data.blocked) {
                    document.getElementById('status').textContent = '접근이 제한되었습니다.';
                    setTimeout(() => { window.location.href = data.redirect_to || '/'; }, 2000);
                } else {
                    document.getElementById('status').textContent =
                        '대기 중... (' + (data.wait_seconds || 0) + '초)';
                }
            } catch (e) {
                document.getElementById('status').textContent = '연결 확인 중...';
            }
        }

        setInterval(checkStatus, 2000);
        checkStatus();
    </script>
</body>
</html>"""


async def handle_queue_enter(request: Request):
    """Enter the queue. Called after AI quiz passes."""
    session_id = (
        request.headers.get("uuid")
        or request.headers.get("x-session-id")
        or request.query_params.get("session_id", "")
    )
    if not session_id:
        return JSONResponse({"error": "session_id required"}, status_code=400)

    r = await get_redis()

    # Mark quiz as passed (in real integration, validate quiz token here)
    await mark_quiz_passed(r, session_id)
    await set_queue_entered(r, session_id)
    metrics.record_queue_enter()

    response = HTMLResponse(QUEUE_PAGE_HTML)
    response.set_cookie("guard_session", session_id, httponly=True, max_age=300)
    return response


async def handle_queue_status(request: Request):
    """Check queue status. Polled by the waiting page every 2 seconds."""
    session_id = (
        request.headers.get("x-session-id")
        or request.cookies.get("guard_session")
        or ""
    )
    if not session_id:
        return JSONResponse({"ready": False, "blocked": True, "reason": "no_session"})

    cfg = get_settings()
    r = await get_redis()

    # Check if quiz was passed
    if not await is_quiz_passed(r, session_id):
        return JSONResponse({
            "ready": False,
            "blocked": True,
            "reason": "quiz_not_passed",
            "redirect_to": cfg.redirect_url,
        })

    # Check wait time
    entered_at = await get_queue_entered_time(r, session_id)
    if not entered_at:
        await set_queue_entered(r, session_id)
        entered_at = int(time.time())

    waited = int(time.time()) - entered_at

    if waited < cfg.queue_wait_min_seconds:
        return JSONResponse({
            "ready": False,
            "blocked": False,
            "wait_seconds": waited,
        })

    # Wait complete → issue queue pass token and 302 redirect
    await issue_queue_pass(r, session_id)
    metrics.record_queue_pass()

    return JSONResponse({
        "ready": True,
        "blocked": False,
        "redirect_to": cfg.upstream_url + "/",
    })
