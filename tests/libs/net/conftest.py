"""Shared fixtures for the link tests."""

from collections.abc import Iterator

import pytest

from bastproxy.libs.net.protocols import PROTOCOLS


@pytest.fixture(autouse=True)
def no_leftover_protocol_clients() -> Iterator[None]:
    """Start and end each test with no logged-in client in the protocol manager (#59)."""
    PROTOCOLS._clients.clear()
    yield
    PROTOCOLS._clients.clear()
