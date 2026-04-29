"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
"""

import time
from flask import request, current_app
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


# Rate limit window in seconds
_RATE_LIMIT_WINDOW = 10


def check_rate_limit(user_id):
    """Check if the user has exceeded the rate limit for placing orders.

    Each user can only place one successful order within a 10-second window.
    Uses a per-app in-memory dictionary to store the last order timestamp.
    Returns True if the request should be blocked (rate limited), False otherwise.
    """
    store = current_app.config.setdefault('_rate_limit_store', {})
    now = time.time()
    last_time = store.get(user_id)
    if last_time is not None and (now - last_time) < _RATE_LIMIT_WINDOW:
        return True
    return False


def record_order(user_id):
    """Record a successful order timestamp for rate limiting."""
    store = current_app.config.setdefault('_rate_limit_store', {})
    store[user_id] = time.time()
