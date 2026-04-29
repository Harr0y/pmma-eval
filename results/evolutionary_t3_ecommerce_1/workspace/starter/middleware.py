"""
T3 E-commerce -- Authentication & Rate-Limiting Middleware (Sample 1)

Mutation Strategy -- Sliding-Window Rate Limiter with OrderedDict:

Instead of a simple "last timestamp per user" dict (fixed-window leaky
bucket), this variant uses a *sliding time window* backed by
``collections.OrderedDict``.  For each user_id the limiter stores a
chronological list of allowed timestamps.  On every check it prunes all
entries older than the window (10 s) before deciding whether to admit the
request.

Why OrderedDict?
  - ``popitem(last=False)`` removes the oldest entry in O(1).
  - Iteration order matches chronological order, so pruning is cheap.
  - No second-pass or sorted() call is needed.

The limiter instance is stored on the Flask app object (``app.extensions``
under the key ``'rate_limiter'``) so that each app created by
``create_app()`` gets a fresh limiter.  This makes test fixtures that
create independent app instances work correctly without cross-test state
leakage.

Existing ``get_current_user()`` is preserved verbatim.
"""

from flask import request, current_app
import sys
import os
import time
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(__file__))

from models import User


# ---------------------------------------------------------------------------
# Auth (unchanged)
# ---------------------------------------------------------------------------

def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Rate limiting -- sliding-window with OrderedDict
# ---------------------------------------------------------------------------

_WINDOW_SECONDS = 10
_MAX_REQUESTS = 1


class SlidingWindowRateLimiter:
    """Per-key sliding-window rate limiter.

    Each key maps to an OrderedDict of timestamps (oldest first).
    On ``allow(key)``:
      1. Prune entries older than ``window`` seconds.
      2. If remaining entries < ``max_requests``, record *now* and return True.
      3. Otherwise return False (rate-limited).

    Parameters
    ----------
    window : float
        Length of the sliding window in seconds.
    max_requests : int
        Maximum number of requests allowed within the window.
    """

    def __init__(self, window: float = _WINDOW_SECONDS, max_requests: int = _MAX_REQUESTS):
        self.window = window
        self.max_requests = max_requests
        # user_id -> OrderedDict[float, None]  (timestamp -> placeholder)
        self._buckets: dict[int, OrderedDict] = {}

    def _prune(self, bucket: OrderedDict, now: float) -> None:
        """Remove timestamps that have fallen outside the sliding window."""
        cutoff = now - self.window
        # popitem(last=False) removes the oldest (leftmost) entry.
        while bucket and next(iter(bucket)) < cutoff:
            bucket.popitem(last=False)

    def allow(self, key: int) -> bool:
        """Check whether *key* is allowed to proceed.

        Returns True and records the timestamp if within quota.
        Returns False if the key has exceeded ``max_requests`` in the
        current sliding window.
        """
        now = time.time()

        if key not in self._buckets:
            self._buckets[key] = OrderedDict()

        bucket = self._buckets[key]
        self._prune(bucket, now)

        if len(bucket) >= self.max_requests:
            return False

        bucket[now] = None  # record this allowed request
        return True

    def reset(self) -> None:
        """Clear all buckets (useful in tests)."""
        self._buckets.clear()


def _get_limiter():
    """Return the SlidingWindowRateLimiter for the current Flask app.

    If no limiter has been attached yet, create one and store it on
    ``app.extensions`` so that each app instance gets its own isolated
    state.
    """
    app = current_app._get_current_object()
    ext = app.extensions
    if 'rate_limiter' not in ext:
        ext['rate_limiter'] = SlidingWindowRateLimiter(
            window=_WINDOW_SECONDS, max_requests=_MAX_REQUESTS,
        )
    return ext['rate_limiter']


def check_rate_limit(user_id: int) -> bool:
    """Check whether *user_id* is within the rate-limit quota.

    Delegates to the per-app SlidingWindowRateLimiter instance.
    Must be called within a request context (or an active app context).

    Returns True if the user is within quota, False otherwise.
    """
    return _get_limiter().allow(user_id)
