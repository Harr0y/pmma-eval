"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
- check_rate_limit(user_id): Check if user is rate-limited.
  Returns (True, None) if allowed, (False, error_response) if blocked.
"""

import time
from flask import request, current_app, jsonify
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

RATE_LIMIT_WINDOW = 10  # seconds


def _get_rate_limits():
    """Get the rate limit dict for the current app (app-scoped)."""
    if '_order_rate_limits' not in current_app.config:
        current_app.config['_order_rate_limits'] = {}
    return current_app.config['_order_rate_limits']


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id):
    """Check if user is within rate limit for placing orders.

    Args:
        user_id: The user's ID.

    Returns:
        (True, None) if the user is allowed to proceed.
        (False, error_response_tuple) if rate-limited (429).
    """
    now = time.time()
    rate_limits = _get_rate_limits()
    last_time = rate_limits.get(user_id)
    if last_time is not None and (now - last_time) < RATE_LIMIT_WINDOW:
        return False, (jsonify({
            'status': 'error',
            'message': 'Rate limit exceeded. Please wait before placing another order.'
        }), 429)
    return True, None


def record_order(user_id):
    """Record an order timestamp for rate limiting."""
    _get_rate_limits()[user_id] = time.time()
