"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Rate limit orders per user.
  Returns (allowed: bool, status_code: int).
"""

from flask import request, current_app
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from models import User

RATE_LIMIT_WINDOW = 10  # seconds


def _get_rate_limit_store() -> dict:
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


def check_rate_limit(user_id: int) -> tuple[bool, int]:
    """Check if the user is allowed to place an order based on rate limit.

    Same user can only submit one successful order per RATE_LIMIT_WINDOW seconds.
    Returns (allowed, status_code) where allowed=True means the request
    should proceed, and status_code is 200 on success or 429 when rate limited.
    """
    store = _get_rate_limit_store()
    now = time.time()
    last_order_time = store.get(user_id)

    if last_order_time is not None and (now - last_order_time) < RATE_LIMIT_WINDOW:
        return False, 429

    store[user_id] = now
    return True, 200
