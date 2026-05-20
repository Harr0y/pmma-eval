"""Shared test fixtures."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Clear rate limit state before each test to ensure isolation."""
    import middleware
    middleware.reset_rate_limits()
    yield
