"""
T3 E-commerce — Authentication Middleware + Rate Limiter (Gen 1, Sample 1)

Implementation strategy (evolutionary variant):
- RateLimiter class encapsulates per-user sliding-window rate limiting.
- Uses time.monotonic() for robust, non-decreasing timestamps.
- State stored on Flask app instance (current_app.extensions) to avoid
  module-level cross-test contamination (lesson from ATU-002 Gen 1 failure).
- Two-phase API: check_rate_limit() before work, record_success() after.
  This avoids recording timestamps for requests that ultimately fail
  (e.g., insufficient stock), which is a design choice that differs from
  recording on every attempt.

Evolutionary notes:
- Inherited: guard clause / early-return pattern, 201 on resource creation.
- Mutation: RateLimiter class with explicit reset() for testability.
- Mutation: state on app instance, NOT module-level dict.
- Mutation: monotonic clock for time measurement.
"""

from flask import request, current_app
import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User


# ── Authentication ────────────────────────────────────────────

def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


# ── Rate Limiter ──────────────────────────────────────────────

class RateLimiter:
    """
    Per-user sliding-window rate limiter backed by an in-memory dict.

    Each user_id maps to the timestamp of their last successful order.
    A new order is blocked if it falls within WINDOW_SECONDS of the last.

    State lives in self._timestamps, which is per-instance. Because the
    RateLimiter instance is stored on the Flask app object, each
    pytest fixture (which calls create_app()) gets a clean instance.
    """

    WINDOW_SECONDS = 10

    def __init__(self):
        self._timestamps = {}  # user_id -> last_success_timestamp

    def check_rate_limit(self, user_id):
        """
        Check whether user_id is currently rate-limited.

        Returns True if the user SHOULD be blocked (rate-limited).
        Returns False if the user is allowed to proceed.
        """
        now = time.monotonic()
        last = self._timestamps.get(user_id)
        if last is None:
            return False
        return (now - last) < self.WINDOW_SECONDS

    def record_success(self, user_id):
        """Record a successful order submission for user_id."""
        self._timestamps[user_id] = time.monotonic()

    def reset(self):
        """Clear all rate-limit state. Useful for testing."""
        self._timestamps.clear()


def get_rate_limiter():
    """
    Get or create the RateLimiter for the current Flask app.

    The limiter is lazily created and stored on app.extensions,
    ensuring each Flask app instance has its own independent state.
    """
    if not hasattr(current_app, 'extensions'):
        current_app.extensions = {}
    return current_app.extensions.setdefault('_rate_limiter', RateLimiter())
