# Project: bastproxy
# Filename: tests/plugins/test_proxy_connected_address.py
#
# File Description: Tests for the proxy plugin's psutil remote-address check
#
# By: Bast
"""Unit tests for `bastproxy.plugins.core.proxy.plugin._proxy.is_connected_address`.

Issue #37: the proxy plugin imported `addr` from the private
`psutil._common` module, which psutil 7.2 no longer defines, so the plugin
exited at import time. These tests pin down that the module imports with the
installed psutil and that remote addresses are recognised by shape.

"""

import importlib
import socket
from collections import namedtuple

import psutil

from bastproxy.plugins.core.proxy.plugin._proxy import is_connected_address

Addr = namedtuple("Addr", ("ip", "port"))


def test_proxy_module_imports_with_installed_psutil() -> None:
    """The proxy plugin module imports without exiting."""
    module = importlib.import_module("bastproxy.plugins.core.proxy.plugin._proxy")

    assert hasattr(module, "ProxyPlugin")


def test_populated_address_is_connected() -> None:
    """An `(ip, port)` named tuple counts as a connected address."""
    assert is_connected_address(Addr("127.0.0.1", 9999)) is True


def test_empty_tuple_is_not_connected() -> None:
    """psutil's empty `raddr` for an unconnected socket is not an address."""
    assert is_connected_address(()) is False


def test_plain_tuple_without_fields_is_not_connected() -> None:
    """A bare tuple lacking `ip`/`port` fields is not an address."""
    assert is_connected_address(("127.0.0.1", 9999)) is False


def test_non_tuple_is_not_connected() -> None:
    """A string (as psutil gives for AF_UNIX paths) is not an address."""
    assert is_connected_address("/tmp/socket") is False


def test_real_psutil_connection_raddr_is_connected() -> None:
    """A live TCP connection's `raddr` from psutil is recognised."""
    with socket.create_server(("127.0.0.1", 0)) as server:
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port)) as client:
            local_port = client.getsockname()[1]
            conns = psutil.Process().net_connections(kind="inet")
            match = [c for c in conns if c.laddr and c.laddr.port == local_port]

            assert match
            assert is_connected_address(match[0].raddr) is True
