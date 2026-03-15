"""Ticket Redirect Guard — session-based bot detection security proxy."""

from guard.middleware import GuardMiddleware

__all__ = ["GuardMiddleware"]
