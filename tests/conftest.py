# Project: bastproxy
# Filename: tests/conftest.py
#
# File Description: Pytest configuration and shared fixtures
#
# By: Bast
"""Pytest configuration and shared fixtures for bastproxy tests.

This module provides common fixtures and configuration for all tests in the
bastproxy test suite.

"""

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure src/ is on the import path so bastproxy.* imports resolve when running tests directly.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests.

    Returns:
        Path: Path to temporary directory that is cleaned up after test.

    """
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def event_loop():
    """Create an event loop for async tests.

    Returns:
        asyncio.AbstractEventLoop: Event loop for async test execution.

    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def mock_api():
    """Create a mock API instance for testing.

    Returns:
        Mock API instance with common methods stubbed.

    """
    from unittest.mock import MagicMock

    from bastproxy.libs.api import API

    mock = MagicMock(spec=API)
    mock.owner_id = "test_owner"
    return mock
