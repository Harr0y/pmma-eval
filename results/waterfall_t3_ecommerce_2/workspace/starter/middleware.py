"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id, window=10): Check if user is within rate limit window.
  Returns (allowed: bool, remaining_seconds: int).
- record_order(user_id): Record the timestamp of a successful order.
- rate_limit_order(user_id, window=10): Alias for check_rate_limit.
  Exported per requirements.md module interface convention.
"""

import time
from flask import request
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# In-memory rate limit storage: {user_id: last_order_timestamp}
_order_timestamps: dict = {}


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id, window=10):
    """
    Check whether the user is within the rate-limit window.

    Args:
        user_id: The user's ID.
        window: Rate-limit window in seconds (default 10).

    Returns:
        (allowed: bool, remaining_seconds: int)
        If the user has placed an order within *window* seconds,
        returns (False, remaining) where *remaining* is the number
        of seconds left until the next order is allowed.
        Otherwise returns (True, 0).
    """
    now = time.time()
    last_time = _order_timestamps.get(user_id)
    if last_time is not None and (now - last_time) < window:
        remaining = int(window - (now - last_time))
        # Ensure at least 1 second remaining to avoid edge-case bypass
        if remaining < 1:
            remaining = 1
        return False, remaining
    return True, 0


def record_order(user_id):
    """Record the timestamp of a successful order for rate limiting."""
    _order_timestamps[user_id] = time.time()


def reset_rate_limits():
    """Clear all rate limit timestamps. Used in test fixtures for isolation."""
    _order_timestamps.clear()


# Alias exported per requirements.md module interface convention
rate_limit_order = check_rate_limit
