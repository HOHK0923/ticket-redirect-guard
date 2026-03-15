from __future__ import annotations

import ipaddress
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kill switch
    guard_enabled: bool = True

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Rate windows (seconds) & limits
    rate_window_short: int = 10
    rate_window_long: int = 60
    rate_limit_short: int = 15
    rate_limit_long: int = 60

    # Score thresholds
    score_mid: int = 30
    score_high: int = 70

    # Delay
    delay_min_ms: int = 100
    delay_max_ms: int = 800

    # Whitelist
    whitelist_ips: str = "127.0.0.1"
    whitelist_paths: str = "/health,/metrics"
    whitelist_uas: str = ""

    # Sensitive paths
    sensitive_paths: str = "/seat,/reserve,/pay,/checkout,/order"

    # Redirect target when bot detected (silent redirect)
    redirect_url: str = "/"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # --- helpers ---

    @staticmethod
    def _parse_csv(value: str) -> list[str]:
        return [s.strip() for s in value.split(",") if s.strip()]

    def get_whitelist_ips(self) -> list[str]:
        return self._parse_csv(self.whitelist_ips)

    def get_whitelist_paths(self) -> list[str]:
        return self._parse_csv(self.whitelist_paths)

    def get_whitelist_uas(self) -> list[str]:
        return self._parse_csv(self.whitelist_uas)

    def get_sensitive_paths(self) -> list[str]:
        return self._parse_csv(self.sensitive_paths)

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
