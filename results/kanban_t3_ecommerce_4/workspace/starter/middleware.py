"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
"""

from flask import request
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# In-memory rate limit store: user_id -> last order timestamp
_rate_limit_store = {}


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id, window_seconds=10):
    """Check if a user is rate limited for order submission.

    Args:
        user_id: The user's ID.
        window_seconds: Minimum seconds between allowed submissions (default 10).

    Returns:
        True if the request is allowed (updates the timestamp),
        False if the user is rate limited.
    """
    now = time.time()
    last_time = _rate_limit_store.get(user_id)
    if last_time is not None and (now - last_time) < window_seconds:
        return False
    _rate_limit_store[user_id] = now
    return True


def reset_rate_limits():
    """Clear all rate limit records. Useful for testing."""
    _rate_limit_store.clear()
