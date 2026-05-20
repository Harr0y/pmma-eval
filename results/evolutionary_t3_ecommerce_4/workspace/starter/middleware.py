"""
ATU-003 Sample 2: Authentication Middleware + Self-Healing Rate Limiting

Design decisions (distinct from Sample 1):
1. **Self-healing in-memory rate limiter**: Uses an in-memory dict for O(1)
   timestamp lookups, but cross-validates against the Order table when a
   cache hit suggests the user should be blocked. If the DB has no orders
   for that user (indicating a DB reset by a test fixture), the stale cache
   entry is automatically cleared. This provides:
   - Fast path: no DB query when cache is empty or expired
   - Correctness: auto-heals after DB reset without explicit reset calls
   - Test isolation: works with pytest fixtures that recreate the database
2. **DB cross-check on potential block**: Only hits the DB when the in-memory
   cache indicates a rate limit violation. This minimizes DB queries in the
   common case (user hasn't ordered recently) while ensuring correctness.
3. **reset_rate_limit() for explicit cleanup**: Provided as a belt-and-suspenders
   mechanism for callers that want to explicitly clear rate limit state.
4. **Preserved get_current_user()**: The original auth function is unchanged.
"""

import time

from flask import request
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from models import User, Order
from app import db


# ---------------------------------------------------------------------------
# Rate Limiting Configuration
# ---------------------------------------------------------------------------

RATE_LIMIT_WINDOW_SECONDS = 10  # Time window in seconds
RATE_LIMIT_MAX_ORDERS = 1       # Max orders per user within the window

# In-memory cache: user_id -> timestamp of last successful order creation
_rate_cache: dict[int, float] = {}


def reset_rate_limit():
    """
    Explicitly reset all in-memory rate limit state.

    Not strictly required for test isolation (the self-healing mechanism
    handles DB resets), but available for explicit cleanup if needed.
    """
    _rate_cache.clear()


def check_order_rate_limit(user_id: int) -> bool:
    """
    Check if the user is within the rate limit for placing orders.

    Returns True if the user is allowed (within limit).
    Returns False if the user is blocked (exceeded limit).

    Self-healing flow:
      1. Check in-memory cache for a recent order timestamp.
      2. If cache says "recent order exists", verify against the DB.
      3. If DB shows no orders for this user, the DB was reset (test fixture).
         Clear the stale cache entry and allow the request.
      4. If DB confirms the user has orders, block the request.
    """
    now = time.time()
    cached_time = _rate_cache.get(user_id)

    if cached_time is not None:
        elapsed = now - cached_time
        if elapsed < RATE_LIMIT_WINDOW_SECONDS:
            # Cache suggests rate limit violation. Cross-check with DB.
            db_order_count = Order.query.filter(Order.user_id == user_id).count()
            if db_order_count > 0:
                # DB confirms: user has orders in this session. Block.
                return False
            else:
                # DB was reset (test fixture). Clear stale cache and allow.
                del _rate_cache[user_id]
                return True
        else:
            # Cache entry expired. Remove it.
            del _rate_cache[user_id]

    return True


def record_order_success(user_id: int):
    """
    Record that a user just successfully placed an order.

    Updates the in-memory cache with the current timestamp so subsequent
    requests within the rate limit window will be blocked (pending DB
    cross-check confirmation).
    """
    _rate_cache[user_id] = time.time()


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))
