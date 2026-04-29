"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication and rate limiting.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
- rate_limit_order(user_id): Rate limiter for order creation.
  Same user can only create 1 order within 10 seconds.
  Returns True if the request is allowed, False if rate-limited.
"""

from flask import request, jsonify
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from models import User

def _get_rate_limit_store():
    """Get the rate limit store for the current Flask app instance.

    Each Flask app instance gets its own rate limit dict stored as an attribute.
    This ensures test fixtures with different app instances don't share rate limits.
    """
    from flask import current_app
    app = current_app._get_current_object()
    if not hasattr(app, '_order_rate_limit'):
        app._order_rate_limit = {}
    return app._order_rate_limit


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


def check_rate_limit(user_id, window_seconds=10):
    """
    Check if a user is rate-limited for order creation.

    Args:
        user_id: The user's ID.
        window_seconds: Time window in seconds (default 10).

    Returns:
        True if the request is allowed, False if rate-limited.
    """
    store = _get_rate_limit_store()
    now = time.time()
    last_time = store.get(user_id)
    if last_time is not None and (now - last_time) < window_seconds:
        return False
    return True


def record_order(user_id):
    """
    Record an order creation timestamp for rate limiting.

    Args:
        user_id: The user's ID.
    """
    store = _get_rate_limit_store()
    store[user_id] = time.time()


def rate_limit_response():
    """Return a 429 Too Many Requests JSON response."""
    return jsonify({
        'status': 'error',
        'message': 'Too many requests. Please try again later.'
    }), 429
