"""
T3 E-commerce — Authentication & Rate Limiting Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Return True if user is rate-limited (submitted
  an order within the last RATE_LIMIT_WINDOW seconds).
  Usage: from middleware import check_rate_limit
"""

from flask import request
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# Rate limiting: in-memory dict mapping user_id -> last order timestamp
_rate_limit_store = {}
RATE_LIMIT_WINDOW = 10  # seconds


def check_rate_limit(user_id):
    """Check if the user is rate-limited for order submission.

    Same user can only submit 1 order per RATE_LIMIT_WINDOW seconds.
    Returns True if rate-limited (caller should return 429), False otherwise.
    """
    now = time.time()
    last_time = _rate_limit_store.get(user_id)
    if last_time is not None and (now - last_time) < RATE_LIMIT_WINDOW:
        return True
    _rate_limit_store[user_id] = now
    return False


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))
