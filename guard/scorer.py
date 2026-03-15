"""Risk score calculator.

Combines multiple signals into a 0-100 integer score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from guard.config import get_settings


@dataclass
class ScoreResult:
    score: int
    reasons: List[str] = field(default_factory=list)


def calculate_risk_score(
    *,
    short_count: int,
    long_count: int,
    has_cookie: bool,
    has_session: bool,
    user_agent: str,
    accept_language: str,
    path: str,
) -> ScoreResult:
    """Return risk score 0-100 with contributing reasons."""
    cfg = get_settings()
    score = 0
    reasons: list[str] = []

    # --- 1. Rate-based scoring ---
    short_ratio = short_count / max(cfg.rate_limit_short, 1)
    long_ratio = long_count / max(cfg.rate_limit_long, 1)

    if short_ratio > 1.0:
        pts = min(int(short_ratio * 30), 40)
        score += pts
        reasons.append(f"short_rate={short_count}/{cfg.rate_limit_short}")
    elif short_ratio > 0.6:
        pts = int(short_ratio * 15)
        score += pts
        reasons.append(f"short_rate_warn={short_count}/{cfg.rate_limit_short}")

    if long_ratio > 1.0:
        pts = min(int(long_ratio * 20), 30)
        score += pts
        reasons.append(f"long_rate={long_count}/{cfg.rate_limit_long}")
    elif long_ratio > 0.6:
        pts = int(long_ratio * 10)
        score += pts
        reasons.append(f"long_rate_warn={long_count}/{cfg.rate_limit_long}")

    # --- 2. Session / cookie ---
    if not has_cookie and not has_session:
        score += 15
        reasons.append("no_cookie_or_session")

    # --- 3. Header stability ---
    if not user_agent or user_agent.strip() == "":
        score += 10
        reasons.append("empty_ua")

    if not accept_language or accept_language.strip() == "":
        score += 5
        reasons.append("no_accept_language")

    # --- 4. Sensitive path weight ---
    sensitive = cfg.get_sensitive_paths()
    if any(path.startswith(sp) for sp in sensitive):
        score += 10
        reasons.append("sensitive_path")

    return ScoreResult(score=min(score, 100), reasons=reasons)
