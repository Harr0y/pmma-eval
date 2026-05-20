"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user

- check_rate_limit(user_id): Check if a user has exceeded the rate limit
  for order creation. Returns True if the request should be blocked.
  Rate limit: 1 order per 10 seconds per user.
"""

from flask import request, current_app
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from models import User

# Rate limit window in seconds
RATE_LIMIT_WINDOW = 10

# Module-level rate limit store (fallback)
_rate_limit_store = {}


def _get_rate_limit_store():
    """Get the rate limit store from the current app, or fall back to module-level."""
    try:
        app = current_app._get_current_object()
        if not hasattr(app, '_rate_limit_store'):
            app._rate_limit_store = {}
        return app._rate_limit_store
    except RuntimeError:
        return _rate_limit_store


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """
    Check if user_id is within the rate limit window.

    Returns True if the request should be BLOCKED (rate limit exceeded).
    Returns False if the request is allowed.

    Rate limit: 1 successful order per 10 seconds per user.
    """
    now = time.time()
    store = _get_rate_limit_store()
    last_time = store.get(user_id)

    if last_time is not None and (now - last_time) < RATE_LIMIT_WINDOW:
        return True  # Blocked

    return False  # Allowed


def record_order_time(user_id):
    """Record the timestamp of a successful order for rate limiting."""
    store = _get_rate_limit_store()
    store[user_id] = time.time()


def reset_rate_limits():
    """Clear all rate limit records. Used for testing."""
    _rate_limit_store.clear()
