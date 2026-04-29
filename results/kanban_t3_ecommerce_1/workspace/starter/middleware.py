"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Check if the user can place an order.
  Returns True if allowed, False if rate-limited (within 10s of last order).
  Usage: from middleware import check_rate_limit
"""

from flask import request
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# Rate limit: track last order timestamp per user_id
_RATE_LIMIT_WINDOW = 10  # seconds
_last_order_time = {}  # user_id -> timestamp


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """Check if the user is allowed to place an order.

    Rate limit: same user_id can only place 1 order per 10 seconds.

    Args:
        user_id: The user's ID (int).

    Returns:
        True if the order is allowed, False if rate-limited.
    """
    now = time.time()
    last = _last_order_time.get(user_id)
    if last is not None and (now - last) < _RATE_LIMIT_WINDOW:
        return False
    _last_order_time[user_id] = now
    return True
