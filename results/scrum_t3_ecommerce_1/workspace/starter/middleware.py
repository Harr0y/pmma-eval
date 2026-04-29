"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Check if user is rate-limited.
  Returns True if the user should be blocked (ordered within last 10s).
- record_order(user_id): Record a successful order for rate limiting.
"""

from flask import request, current_app
import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

RATE_LIMIT_WINDOW = 10  # seconds


def _get_order_timestamps():
    """Get the rate-limit timestamp dict for the current app instance."""
    if not hasattr(current_app, '_order_timestamps'):
        current_app._order_timestamps = {}
    return current_app._order_timestamps


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """Check if a user is rate-limited for creating orders.

    Returns True if the user is rate-limited (ordered within the last 10 seconds).
    Returns False if the user is allowed to proceed.
    """
    timestamps = _get_order_timestamps()
    now = time.time()
    if user_id in timestamps:
        if now - timestamps[user_id] < RATE_LIMIT_WINDOW:
            return True  # Rate limited
    return False  # Allowed


def record_order(user_id):
    """Record a successful order for rate limiting purposes."""
    timestamps = _get_order_timestamps()
    timestamps[user_id] = time.time()
