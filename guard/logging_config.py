"""Structured JSON logging setup."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        # Merge extra fields
        for key in ("guard", "server_request_log", "domain_event"):
            data = getattr(record, key, None)
            if data and isinstance(data, dict):
                log_entry[key] = data
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("guard")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger
