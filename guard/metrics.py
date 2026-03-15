"""In-memory metrics for the guard middleware."""

from __future__ import annotations

import threading
import time


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.redirect_count = 0
        self.pass_count = 0
        self.delay_total_ms = 0.0
        self.delay_count = 0
        self._start_time = time.time()

    def record_pass(self) -> None:
        with self._lock:
            self.pass_count += 1

    def record_redirect(self) -> None:
        with self._lock:
            self.redirect_count += 1

    def record_delay(self, ms: float) -> None:
        with self._lock:
            self.delay_total_ms += ms
            self.delay_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            avg = (
                round(self.delay_total_ms / self.delay_count, 1)
                if self.delay_count > 0
                else 0.0
            )
            return {
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "redirect_count": self.redirect_count,
                "pass_count": self.pass_count,
                "delay_count": self.delay_count,
                "avg_delay_ms": avg,
            }


metrics = Metrics()
