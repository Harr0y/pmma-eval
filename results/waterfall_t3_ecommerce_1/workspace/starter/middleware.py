"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Check if user is rate limited (10s cooldown per user).
- record_order_success(user_id): Record successful order timestamp for rate limiting.
"""

import time

from flask import request
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# Rate limit store: {user_id: last_success_timestamp}
_rate_limit_store = {}


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """Check if user is rate limited.

    Returns True if the user is allowed to proceed, False if rate limited.
    Same user can only successfully submit 1 order within 10 seconds.
    """
    now = time.time()
    last_time = _rate_limit_store.get(user_id, 0)
    if now - last_time < 10:
        return False
    return True


def record_order_success(user_id):
    """Record successful order timestamp for rate limiting."""
    _rate_limit_store[user_id] = time.time()


def reset_rate_limits():
    """Clear all rate limit records. Used by test fixtures for isolation."""
    _rate_limit_store.clear()
