"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Check if user is within rate limit.
  Returns True if allowed, False if rate limited.
- update_rate_limit(user_id): Record a successful order for rate limiting.
"""

from flask import request
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from models import User

_order_timestamps = {}


def get_current_user():
    """Get the current user from X-User-Id header.
    Returns User object or None if not found/invalid."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        return None
    return User.query.get(uid)


def check_rate_limit(user_id):
    """Check if user is within rate limit (1 order per 10 seconds).
    Returns True if allowed, False if rate limited.
    NOTE: Does NOT update the timestamp. Call update_rate_limit() after successful order."""
    now = time.time()
    last_time = _order_timestamps.get(user_id, 0)
    if now - last_time < 10:
        return False
    return True


def update_rate_limit(user_id):
    """Record a successful order for rate limiting purposes.
    Call this ONLY after an order is successfully created."""
    _order_timestamps[user_id] = time.time()
