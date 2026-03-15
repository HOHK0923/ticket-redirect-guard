"""In-memory metrics for the guard middleware."""

from __future__ import annotations

import threading
import time


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.redirect_count = 0
        self.pass_count = 0
        self.queue_enter_count = 0
        self.queue_pass_count = 0
        self.queue_block_count = 0
        self._start_time = time.time()

    def record_pass(self) -> None:
        with self._lock:
            self.pass_count += 1

    def record_redirect(self) -> None:
        with self._lock:
            self.redirect_count += 1

    def record_queue_enter(self) -> None:
        with self._lock:
            self.queue_enter_count += 1

    def record_queue_pass(self) -> None:
        with self._lock:
            self.queue_pass_count += 1

    def record_queue_block(self) -> None:
        with self._lock:
            self.queue_block_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "redirect_count": self.redirect_count,
                "pass_count": self.pass_count,
                "queue_enter_count": self.queue_enter_count,
                "queue_pass_count": self.queue_pass_count,
                "queue_block_count": self.queue_block_count,
            }


metrics = Metrics()
