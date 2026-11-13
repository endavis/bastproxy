"""Tests for MudProxy._apply_cli_overrides (#428)."""

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy import MudProxy


def _proxy(current: dict[str, Any], reject: set[Any]) -> tuple[MagicMock, list[tuple[str, Any]]]:
    sets: list[tuple[str, Any]] = []
    proxy = MagicMock()

    def set_(_pid: str, setting: str, value: Any) -> bool:
        if value in reject:
            raise ValueError("rejected")
        sets.append((setting, value))
        return True

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.get":
            return lambda _pid, setting: current[setting]
        return set_

    proxy.api = api
    return proxy, sets


def _run(proxy: MagicMock, port: Any, address: Any) -> None:
    MudProxy._apply_cli_overrides(proxy, {"port": port, "IPv4_address": address})


def test_port_is_stored() -> None:
    proxy, sets = _proxy({"listenport": 9999, "ipv4address": "localhost"}, set())
    _run(proxy, "9998", "")
    assert sets == [("listenport", "9998")]


def test_bad_port_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    proxy, sets = _proxy({"listenport": 9999, "ipv4address": "localhost"}, {"99999"})
    with caplog.at_level(logging.ERROR):
        _run(proxy, "99999", "")
    assert sets == []


def test_defaults_do_nothing() -> None:
    proxy, sets = _proxy({"listenport": 9999, "ipv4address": "localhost"}, set())
    _run(proxy, -1, "")
    assert sets == []


def test_bad_address_not_stored() -> None:
    proxy, sets = _proxy({"listenport": 9999, "ipv4address": "localhost"}, {"bad host"})
    _run(proxy, -1, "bad host")
    assert sets == []


def test_address_stored() -> None:
    proxy, sets = _proxy({"listenport": 9999, "ipv4address": "localhost"}, set())
    _run(proxy, -1, "127.0.0.1")
    assert sets == [("ipv4address", "127.0.0.1")]
