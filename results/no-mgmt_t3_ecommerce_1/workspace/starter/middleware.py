"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Rate limit per user (1 order per 10s).
  Returns True if the request is allowed, False if rate-limited.
"""

from flask import request, current_app
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from models import User

RATE_LIMIT_WINDOW = 10  # seconds


def _get_rate_store():
    """Get the rate limit store for the current app."""
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
    Check if the user is within the rate limit.

    A user can place at most 1 order per RATE_LIMIT_WINDOW seconds.
    Returns True if allowed, False if rate-limited.
    """
    now = time.time()
    store = _get_rate_store()
    last_time = store.get(user_id)
    if last_time is not None and (now - last_time) < RATE_LIMIT_WINDOW:
        return False
    store[user_id] = now
    return True
