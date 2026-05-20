"""
T3 E-commerce — Authentication & Rate-Limiting Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Check if a user is within rate limits.
  Returns (is_allowed: bool, remaining_seconds: int).
"""

import time
from flask import request, current_app
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

RATE_LIMIT_WINDOW = 10  # seconds


def _get_rate_limit_store():
    """Get the rate limit store for the current app instance."""
    if not hasattr(current_app, '_rate_limit_store'):
        current_app._rate_limit_store = {}
    return current_app._rate_limit_store


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """Check if user_id is within the rate limit.

    A user can only place one order every RATE_LIMIT_WINDOW seconds.

    Args:
        user_id: The user's ID (int).

    Returns:
        (is_allowed, remaining_seconds): Whether the request is allowed,
        and if not, how many seconds remain until the next request is allowed.
    """
    now = time.time()
    store = _get_rate_limit_store()
    last_time = store.get(user_id)
    if last_time is None or (now - last_time) >= RATE_LIMIT_WINDOW:
        return True, 0
    remaining = int(RATE_LIMIT_WINDOW - (now - last_time))
    if remaining <= 0:
        remaining = 1
    return False, remaining


def record_order(user_id):
    """Record an order timestamp for rate limiting.

    Args:
        user_id: The user's ID (int).
    """
    _get_rate_limit_store()[user_id] = time.time()
