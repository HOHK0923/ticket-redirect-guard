"""In-memory metrics for the queue system."""

from __future__ import annotations

import threading
import time


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.queue_enter_count = 0
        self.queue_pass_count = 0
        self.proxy_count = 0
        self.blocked_count = 0
        self._start_time = time.time()

    def record_queue_enter(self) -> None:
        with self._lock:
            self.queue_enter_count += 1

    def record_queue_pass(self) -> None:
        with self._lock:
            self.queue_pass_count += 1

    def record_proxy(self) -> None:
        with self._lock:
            self.proxy_count += 1

    def record_blocked(self) -> None:
        with self._lock:
            self.blocked_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "queue_enter_count": self.queue_enter_count,
                "queue_pass_count": self.queue_pass_count,
                "proxy_count": self.proxy_count,
                "blocked_count": self.blocked_count,
            }


metrics = Metrics()
