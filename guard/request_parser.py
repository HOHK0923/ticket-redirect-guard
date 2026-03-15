"""Extract structured data from incoming requests for session tracking."""

from __future__ import annotations

import re
import uuid as uuid_mod

from starlette.requests import Request

# Endpoint path patterns matching the backend API
TICKETING_RE = re.compile(r"/api/ticketing/(\d+)/(seatmap|hold/seat)")
BOOKING_RE = re.compile(r"/api/bookings(?:/([^/]+)/payment-ready)?")
PAYMENT_RE = re.compile(r"/api/payments/(confirm|fail)")

# Domain event name mapping: (endpoint_pattern, http_method) → event_name
EVENT_MAP = {
    "seatmap": "seatmap_view",
    "hold/seat": "seat_hold_attempt",
    "bookings_create": "checkout_enter",
    "payment-ready": "payment_attempt",
    "confirm": "payment_success",
    "fail": "payment_fail",
}


def extract_session_id(request: Request) -> str:
    """Extract session UUID from headers. Generate one if missing."""
    sid = (
        request.headers.get("uuid")
        or request.headers.get("x-session-id")
        or request.headers.get("x-session-ticket")
    )
    if not sid:
        # Fallback: use IP + UA hash as pseudo-session
        ip = request.client.host if request.client else "0.0.0.0"
        ua = request.headers.get("user-agent", "")
        sid = uuid_mod.uuid5(uuid_mod.NAMESPACE_DNS, f"{ip}|{ua}").hex
    return sid


def extract_user_id(request: Request) -> str:
    return request.headers.get("x-user-id", "")


def extract_session_ticket(request: Request) -> str:
    return request.headers.get("x-session-ticket", "")


def extract_device_id(request: Request) -> str:
    return request.headers.get("x-device-id", "")


def extract_show_schedule_id(path: str) -> int | None:
    m = TICKETING_RE.match(path)
    return int(m.group(1)) if m else None


def extract_target_key(path: str, body: dict | None = None) -> str:
    """Build a target key for retry tracking.

    - Ticketing: "{showScheduleId}:{seatId}"
    - Booking/Payment: "{orderId}"
    """
    # Ticketing endpoints
    m = TICKETING_RE.match(path)
    if m:
        schedule_id = m.group(1)
        seat_ids = ""
        if body and "seatIds" in body:
            seat_ids = ",".join(str(s) for s in sorted(body["seatIds"]))
        elif body and "seatId" in body:
            seat_ids = str(body["seatId"])
        return f"{schedule_id}:{seat_ids}" if seat_ids else schedule_id

    # Booking payment-ready
    m = BOOKING_RE.match(path)
    if m and m.group(1):
        return m.group(1)  # reservationNumber

    # Payment endpoints
    if body and "orderId" in body:
        return body["orderId"]

    return ""


def normalize_endpoint(path: str) -> str:
    """Normalize endpoint path by replacing IDs with placeholders."""
    path = TICKETING_RE.sub(r"/api/ticketing/{id}/\2", path)
    path = re.sub(r"/api/bookings/[^/]+/payment-ready", "/api/bookings/{id}/payment-ready", path)
    return path


def map_to_domain_event(path: str, method: str = "GET", status: int = 200) -> str | None:
    """Map an endpoint call to a domain event name."""
    m = TICKETING_RE.match(path)
    if m:
        action = m.group(2)  # "seatmap" or "hold/seat"
        return EVENT_MAP.get(action)

    m = BOOKING_RE.match(path)
    if m:
        if m.group(1):  # /api/bookings/{id}/payment-ready
            return EVENT_MAP.get("payment-ready")
        elif method.upper() == "POST":
            return EVENT_MAP.get("bookings_create")
        return None

    m = PAYMENT_RE.match(path)
    if m:
        return EVENT_MAP.get(m.group(1))

    return None
