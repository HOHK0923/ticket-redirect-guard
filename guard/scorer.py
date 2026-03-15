"""Risk score calculator based on AI pipeline features.

Computes 3 behavioral features from session request history:
  1. endpoint_burst_max_1s: rapid calls to same endpoint
  2. req_interval_cv: regularity of request timing
  3. target_retry_count: repeated attempts on same target
"""

from __future__ import annotations

import math

from guard.config import get_settings
from guard.models import ScoreResult, SessionRequestRecord


def compute_endpoint_burst_max_1s(
    history: list[SessionRequestRecord],
    current_endpoint: str,
) -> int:
    """Max calls to the same endpoint within any 1-second window.

    Uses O(n) two-pointer sliding window.
    """
    timestamps = sorted(
        r.ts_ms for r in history if r.endpoint == current_endpoint
    )
    if len(timestamps) <= 1:
        return len(timestamps)

    max_burst = 1
    left = 0
    for right in range(len(timestamps)):
        while timestamps[right] - timestamps[left] > 1000:
            left += 1
        max_burst = max(max_burst, right - left + 1)

    return max_burst


def compute_req_interval_cv(history: list[SessionRequestRecord]) -> float:
    """Coefficient of Variation of request intervals.

    CV = stddev / mean
    Returns 1.0 (human-like) if fewer than 3 requests.
    """
    if len(history) < 3:
        return 1.0

    timestamps = sorted(r.ts_ms for r in history)
    intervals = [
        timestamps[i + 1] - timestamps[i]
        for i in range(len(timestamps) - 1)
    ]

    if not intervals:
        return 1.0

    mean = sum(intervals) / len(intervals)
    if mean == 0:
        return 0.0  # all same timestamp = very suspicious

    variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    return math.sqrt(variance) / mean


def compute_target_retry_count(
    history: list[SessionRequestRecord],
    current_target_key: str,
) -> int:
    """Count how many times the same target was accessed in this session."""
    if not current_target_key:
        return 0
    return sum(1 for r in history if r.target_key == current_target_key)


def calculate_risk_score(
    history: list[SessionRequestRecord],
    current_endpoint: str,
    current_target_key: str,
) -> ScoreResult:
    """Calculate risk score from session behavior. Score: 0-100."""
    cfg = get_settings()
    score = 0
    reasons: list[str] = []

    # Feature 1: Endpoint burst (0-40 points)
    burst = compute_endpoint_burst_max_1s(history, current_endpoint)
    if burst >= cfg.burst_threshold:
        pts = min(40, (burst - cfg.burst_threshold + 1) * 12)
        score += pts
        reasons.append(f"burst={burst}")

    # Feature 2: Request interval CV (0-40 points)
    cv = compute_req_interval_cv(history)
    if len(history) >= 3 and cv < cfg.cv_threshold:
        pts = min(40, int((cfg.cv_threshold - cv) / cfg.cv_threshold * 40))
        score += pts
        reasons.append(f"cv={cv:.3f}")

    # Feature 3: Target retry count (0-50 points)
    retries = compute_target_retry_count(history, current_target_key)
    if retries >= cfg.retry_threshold:
        pts = min(50, (retries - cfg.retry_threshold + 1) * 10)
        score += pts
        reasons.append(f"retries={retries}")

    features = {
        "endpoint_burst_max_1s": burst,
        "req_interval_cv": round(cv, 3),
        "target_retry_count": retries,
    }

    return ScoreResult(
        score=min(score, 100),
        reasons=reasons,
        features=features,
    )
