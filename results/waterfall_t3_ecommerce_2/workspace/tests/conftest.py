"""
Test configuration — auto-reset rate limit state between tests.

The in-memory rate limit dictionary (_order_timestamps in middleware.py)
persists across test functions. This autouse fixture clears it before
every test so that rate limiting does not leak between isolated test cases.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from middleware import reset_rate_limits


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Reset rate limit state before each test."""
    reset_rate_limits()
    yield
