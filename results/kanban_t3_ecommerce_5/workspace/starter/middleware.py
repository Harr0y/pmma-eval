"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Rate-limit order creation per user.
"""

from flask import request, current_app
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from models import User

# Rate limit window in seconds
_RATE_LIMIT_WINDOW = 10


def _get_order_timestamps():
    """Get the per-app rate limit timestamp dict.

    Stored on current_app so each new app instance (e.g. pytest
    fixtures calling create_app()) starts with clean state, avoiding
    cross-test pollution from a module-level global.
    """
    timestamps = getattr(current_app, '_order_timestamps', None)
    if timestamps is None:
        timestamps = {}
        current_app._order_timestamps = timestamps
    return timestamps


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """Check if the user is within the rate limit for order creation.

    Args:
        user_id: The integer user ID.

    Returns:
        A tuple (allowed, status_code) where allowed is True if the
        request should proceed, False if it should be rejected.
        When allowed is False, status_code is 429.
    """
    now = time.time()
    order_timestamps = _get_order_timestamps()
    last_time = order_timestamps.get(user_id)
    if last_time is not None and (now - last_time) < _RATE_LIMIT_WINDOW:
        return (False, 429)
    order_timestamps[user_id] = now
    return (True, 200)
