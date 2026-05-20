"""
Shared test conftest for T3 E-commerce system.

Provides fixtures and autouse hooks for test isolation.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Reset in-memory rate limit timestamps before each test.

    The middleware._order_timestamps dict persists across tests because it is
    module-level. Each test's client fixture recreates the database but does
    not clear this dict, causing rate limit state to leak between tests.
    """
    from middleware import _order_timestamps
    _order_timestamps.clear()
    yield
