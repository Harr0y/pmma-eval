"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
- check_rate_limit(user_id): Check if user is within rate limit.
- record_order_time(user_id): Record successful order timestamp.

Usage:
  from middleware import get_current_user, check_rate_limit, record_order_time
"""

from flask import request
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from models import User

# Rate limiting: stores {user_id: last_success_timestamp}
_order_timestamps = {}


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    try:
        return User.query.get(int(user_id))
    except ValueError:
        return None


def check_rate_limit(user_id: int) -> bool:
    """
    Check whether the user is within the order rate limit.

    Returns True if the user is allowed to place an order,
    False if the user has exceeded the rate limit.
    """
    now = time.time()
    last_time = _order_timestamps.get(user_id, 0)
    return (now - last_time) >= 10  # 10-second window


def record_order_time(user_id: int) -> None:
    """Record the timestamp of a successful order (call only after order creation succeeds)."""
    _order_timestamps[user_id] = time.time()


def reset_rate_limits() -> None:
    """Reset all rate limit timestamps. Used by tests to ensure isolation between test cases."""
    _order_timestamps.clear()
