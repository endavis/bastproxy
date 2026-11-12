"""Shared fixtures for the link tests."""

from collections.abc import Iterator

import pytest

from bastproxy.libs.net.naws import WINDOW_SIZE
from bastproxy.libs.net.protocols import PROTOCOLS


@pytest.fixture(autouse=True)
def no_leftover_protocol_clients() -> Iterator[None]:
    """Start and end each test with no logged-in client in the protocol manager (#59)."""
    PROTOCOLS._clients.clear()
    yield
    PROTOCOLS._clients.clear()


@pytest.fixture(autouse=True)
def no_leftover_window_size() -> Iterator[None]:
    """Start and end each test with a fresh window size forwarder (#308)."""
    WINDOW_SIZE.reset()
    yield
    WINDOW_SIZE.reset()
