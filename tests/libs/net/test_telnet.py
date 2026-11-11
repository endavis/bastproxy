"""Tests for bastproxy.libs.net.telnet and the telnetlib3.telopt table (#67)."""

import importlib

import telnetlib3.telopt

from bastproxy.libs.net import telnet


def test_go_ahead_bytes() -> None:
    assert telnet.go_ahead() == b"\xff\xf9"


def test_end_of_record_bytes() -> None:
    assert telnet.end_of_record() == b"\xff\xef"


def test_constants_come_from_telopt() -> None:
    for name in ("IAC", "GA"):
        assert getattr(telnet, name) is getattr(telnetlib3.telopt, name)


def test_importing_net_package_does_not_patch_telopt() -> None:
    """Importing the package must not add names to telnetlib3.telopt."""
    before = set(dir(telnetlib3.telopt))
    debug_before = dict(telnetlib3.telopt._DEBUG_OPTS)
    importlib.reload(importlib.import_module("bastproxy.libs.net"))
    assert set(dir(telnetlib3.telopt)) == before
    assert dict(telnetlib3.telopt._DEBUG_OPTS) == debug_before
    assert not hasattr(telnetlib3.telopt, "A102")
