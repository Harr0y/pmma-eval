"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Rate limiting per user (1 order per 10 seconds).
  Returns True if the request is allowed, False if rate limited.
"""

from flask import request, current_app
import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

RATE_LIMIT_WINDOW = 10  # seconds


def _get_rate_limit_store():
    """Get or create the rate limit store on the current app."""
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
    """
    Check if the user is within rate limit (1 order per 10 seconds).

    Args:
        user_id: The user's ID.

    Returns:
        True if the request is allowed, False if rate limited.
    """
    store = _get_rate_limit_store()
    now = time.time()
    last_order_time = store.get(user_id)
    if last_order_time is not None and (now - last_order_time) < RATE_LIMIT_WINDOW:
        return False
    store[user_id] = now
    return True
