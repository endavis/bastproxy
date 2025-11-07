# -*- coding: utf-8 -*-
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
import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil


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
    from libs.api import API

    mock = MagicMock(spec=API)
    mock.owner_id = "test_owner"
    return mock
