"""
T3 Ecommerce - Authentication & Rate Limiting Middleware (Sample 3)

Key design decision (fixing Gen 1 root cause):
- Rate limit state is stored on the Flask app object, NOT in a module-level dict.
  This ensures state resets when pytest fixtures create new app instances,
  while persisting across requests within the same app lifecycle.

Inherited traits:
- get_current_user() returns (user, error_response) tuple pattern.
- Two-phase rate limiting: check_rate_limit() before processing,
  mark_rate_limit_success() only after successful commit.

Cross-inherited traits:
- Reusable auth helper with tuple return for composable error handling.
"""

import time
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import request, jsonify, current_app
from models import User

RATE_LIMIT_WINDOW = 10  # seconds


def _get_rate_store():
    """Return the rate limit store bound to the current Flask app instance.

    Module-level dicts persist across pytest fixtures (different app instances),
    causing false 429 responses. Storing on the app object ensures:
    - Same test (same app): state persists across requests (needed for rapid-order test).
    - Different tests (new app): state resets automatically.
    """
    app = current_app._get_current_object()
    if not hasattr(app, '_rate_limit_store'):
        app._rate_limit_store = {}
    return app._rate_limit_store


def get_current_user():
    """Get the current user from X-User-Id header.

    Returns:
        (user, error_response) tuple.
        - If authenticated: (User, None)
        - If missing header: (None, (json_response, 401))
    """
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None, (jsonify({'status': 'error', 'message': 'Authentication required'}), 401)
    user = User.query.get(int(user_id))
    if user is None:
        return None, (jsonify({'status': 'error', 'message': 'User not found'}), 401)
    return user, None


def check_rate_limit(user_id):
    """Check if user_id is within rate limit window.

    Returns:
        True if the user is rate-limited (should be blocked).
        False if the user is free to proceed.
    """
    store = _get_rate_store()
    now = time.time()
    last_success = store.get(user_id)
    if last_success is not None and (now - last_success) < RATE_LIMIT_WINDOW:
        return True
    return False


def mark_rate_limit_success(user_id):
    """Record a successful order for user_id. Call only after commit."""
    store = _get_rate_store()
    store[user_id] = time.time()
