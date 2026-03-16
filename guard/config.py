from __future__ import annotations

from functools import cached_property, lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kill switch
    guard_enabled: bool = True

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Upstream backend server to proxy to
    upstream_url: str = "http://localhost:8080"

    # --- Queue ---
    queue_wait_min_seconds: int = 3  # minimum wait time in queue
    queue_pass_ttl_seconds: int = 300  # queue pass token lifetime (5 min)

    # --- Session ---
    session_ttl_seconds: int = 600  # session data TTL (10 min)

    # --- Sensitive endpoint patterns (require queue pass) ---
    sensitive_paths: str = "/api/ticketing,/api/bookings,/api/payments"

    # Redirect URL (blocked / no queue pass)
    redirect_url: str = "/"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # --- helpers ---

    @staticmethod
    def _parse_csv(value: str) -> list[str]:
        return [s.strip() for s in value.split(",") if s.strip()]

    @cached_property
    def _sensitive_paths(self) -> list[str]:
        return self._parse_csv(self.sensitive_paths)

    def get_sensitive_paths(self) -> list[str]:
        return self._sensitive_paths


@lru_cache
def get_settings() -> Settings:
    return Settings()
