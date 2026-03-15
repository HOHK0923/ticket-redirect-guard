"""Example: mock backend server matching the ticketing API patterns.

This simulates the backend that the security proxy protects.
Users never connect to this directly in production.

Run:
    uvicorn examples.backend_app:app --port 8080
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi import FastAPI

app = FastAPI(title="Ticketing Backend (Mock)")


@app.get("/")
async def home():
    return {"page": "Welcome to Ticketing"}


@app.get("/api/ticketing/{show_schedule_id}/seatmap")
async def seatmap(show_schedule_id: int):
    return {"showScheduleId": show_schedule_id, "seats": ["A1", "A2", "A3", "B1", "B2"]}


@app.post("/api/ticketing/{show_schedule_id}/hold/seat")
async def hold_seat(show_schedule_id: int):
    return {"status": "held", "showScheduleId": show_schedule_id}


@app.post("/api/bookings")
async def create_booking():
    return {"reservationNumber": "RSV-20260315-0001", "status": "created"}


@app.post("/api/bookings/{reservation_number}/payment-ready")
async def payment_ready(reservation_number: str):
    return {"reservationNumber": reservation_number, "status": "payment_ready"}


@app.post("/api/payments/confirm")
async def payment_confirm():
    return {"status": "confirmed", "orderId": "ORD-20260315-0001"}


@app.get("/api/payments/fail")
async def payment_fail():
    return {"status": "failed", "error_code": "TIMEOUT"}


@app.get("/health")
async def health():
    return {"status": "ok"}
