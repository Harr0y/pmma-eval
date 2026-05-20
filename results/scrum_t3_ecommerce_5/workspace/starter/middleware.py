"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Check if user is rate-limited.
  Returns True if request is allowed, False if rate-limited.
  Same user can submit at most 1 order per 10 seconds.
"""

from flask import request
import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# In-memory rate limit store: user_id -> timestamp of last allowed request
_rate_limit_store = {}
_RATE_LIMIT_WINDOW = 10  # seconds


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """Check if the user is allowed to place an order.

    Rate limit: at most 1 order per 10 seconds per user.

    Args:
        user_id: The user's ID (int or str).

    Returns:
        True if the request is allowed, False if rate-limited.
    """
    now = time.time()
    last_time = _rate_limit_store.get(user_id)
    if last_time is not None and (now - last_time) < _RATE_LIMIT_WINDOW:
        return False
    _rate_limit_store[user_id] = now
    return True


def reset_rate_limit():
    """Clear all rate limit records. Useful for testing."""
    _rate_limit_store.clear()
