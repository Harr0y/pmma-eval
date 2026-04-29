"""
T3 E-commerce — Authentication & Rate Limiting Middleware (Sample 3)

Evolutionary variant: rate limiter state is stored in
flask.current_app.extensions['rate_log'] instead of a module-level dict.

Why this matters: each call to create_app() produces a fresh Flask app with
an empty extensions dict.  When the test fixture calls db.drop_all() +
db.create_all() inside a new app context, the rate limiter state is also
reset automatically -- no cross-test leakage.

Design: check/record separation
- check_rate_limit(user_id): read-only check, returns True if blocked
- record_successful_order(user_id): append timestamp after commit succeeds
This prevents ghost entries from failed orders.
"""

import time
from collections import defaultdict
from flask import request, current_app

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# --- Rate limiter constants ---
_RATE_WINDOW = 10  # seconds
_RATE_LIMIT = 1    # max orders per window per user


def _get_rate_log():
    """Return the per-app rate log defaultdict(list), creating it if needed."""
    if 'rate_log' not in current_app.extensions:
        current_app.extensions['rate_log'] = defaultdict(list)
    return current_app.extensions['rate_log']


# --- Authentication ---

def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


# --- Rate limiting (check/record separation) ---

def check_rate_limit(user_id):
    """Check whether user_id has exceeded the order rate limit.

    Returns True if the request should be blocked (429).
    This function is read-only -- it does NOT record a timestamp.
    """
    rate_log = _get_rate_log()
    now = time.time()
    # Keep only timestamps within the window
    rate_log[user_id] = [t for t in rate_log[user_id] if now - t < _RATE_WINDOW]
    return len(rate_log[user_id]) >= _RATE_LIMIT


def record_successful_order(user_id):
    """Record a successful order timestamp for rate limiting.

    Call this AFTER db.session.commit() succeeds so that failed orders
    do not consume the rate limit quota.
    """
    rate_log = _get_rate_log()
    rate_log[user_id].append(time.time())
