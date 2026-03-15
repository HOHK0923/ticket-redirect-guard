"""Data models for the guard system, aligned with bot-detection AI pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class SessionRequestRecord:
    """Compact record stored in Redis per request, used for feature computation."""
    endpoint: str
    ts_ms: int
    target_key: str  # "{showScheduleId}:{seatId}" or "{orderId}" or ""


@dataclass
class ServerRequestLog:
    """Full server request log, aligned with the AI pipeline schema."""
    session_id: str
    user_id: str
    session_ticket: str
    endpoint: str
    ts_ms_server: int
    status: int
    latency_ms: int
    ip: str
    device_id: str
    request_id: str
    show_schedule_id: int | None = None
    seat_ids: list[int] = field(default_factory=list)
    order_id: str | None = None
    error_code: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DomainEventLog:
    """Funnel stage event, aligned with the AI pipeline schema."""
    event_name: str
    ts_ms: int
    session_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScoreResult:
    score: int
    reasons: list[str] = field(default_factory=list)
    features: dict = field(default_factory=dict)
