from __future__ import annotations

import ipaddress
from functools import cached_property, lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kill switch
    guard_enabled: bool = True

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Upstream backend server to proxy to
    upstream_url: str = "http://localhost:8080"

    # --- Session tracking ---
    session_idle_timeout_seconds: int = 60

    # --- AI feature thresholds ---
    # endpoint_burst_max_1s: max calls to same endpoint in 1 second
    burst_threshold: int = 3

    # req_interval_cv: coefficient of variation of request intervals
    # LOWER cv = more suspicious (mechanical/bot-like)
    cv_threshold: float = 0.15

    # target_retry_count: same target retried N+ times
    retry_threshold: int = 3

    # --- Score threshold ---
    score_high: int = 60  # score >= this → block (302 redirect)

    # --- Queue ---
    queue_wait_min_seconds: int = 3  # minimum wait time in queue

    # --- Whitelist ---
    whitelist_ips: str = ""
    whitelist_paths: str = "/_guard/health,/_guard/metrics"
    whitelist_uas: str = ""

    # --- Sensitive endpoint patterns ---
    sensitive_paths: str = "/api/ticketing,/api/bookings,/api/payments"

    # Redirect target when bot detected (silent redirect)
    redirect_url: str = "/"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # --- helpers ---

    @staticmethod
    def _parse_csv(value: str) -> list[str]:
        return [s.strip() for s in value.split(",") if s.strip()]

    @cached_property
    def _whitelist_ips(self) -> list[str]:
        return self._parse_csv(self.whitelist_ips)

    @cached_property
    def _whitelist_paths(self) -> list[str]:
        return self._parse_csv(self.whitelist_paths)

    @cached_property
    def _whitelist_uas(self) -> list[str]:
        return self._parse_csv(self.whitelist_uas)

    @cached_property
    def _sensitive_paths(self) -> list[str]:
        return self._parse_csv(self.sensitive_paths)

    def get_whitelist_ips(self) -> list[str]:
        return self._whitelist_ips

    def get_whitelist_paths(self) -> list[str]:
        return self._whitelist_paths

    def get_whitelist_uas(self) -> list[str]:
        return self._whitelist_uas

    def get_sensitive_paths(self) -> list[str]:
        return self._sensitive_paths

    def is_ip_whitelisted(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for entry in self.get_whitelist_ips():
            try:
                if "/" in entry:
                    if addr in ipaddress.ip_network(entry, strict=False):
                        return True
                else:
                    if addr == ipaddress.ip_address(entry):
                        return True
            except ValueError:
                continue
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
