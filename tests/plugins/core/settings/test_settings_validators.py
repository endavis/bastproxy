"""Tests for the shared setting validators and the validated defaults (#428)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin
from bastproxy.plugins.core.events.plugin._events import EventsPlugin
from bastproxy.plugins.core.proxy.plugin import _proxy
from bastproxy.plugins.core.proxy.plugin._proxy import ProxyPlugin
from bastproxy.plugins.core.settings import (
    int_range,
    validate_ipv4_host,
    validate_ipv6_host,
    validate_port,
    validate_port_or_unset,
)
from bastproxy.plugins.debug.records.plugin._records import RecordPlugin


def test_int_range_boundaries_and_label() -> None:
    check = int_range(1, 5, label="thing")
    assert check(1) == ""
    assert check(5) == ""
    assert "thing" in check(0)
    assert "thing" in check(6)
    assert check(True) != ""
    assert check("3") != ""
    assert int_range(0)(0) == ""
    assert int_range(0)(-1) != ""


def test_ports() -> None:
    assert validate_port(1) == ""
    assert validate_port(65535) == ""
    assert validate_port(0) != ""
    assert validate_port(65536) != ""
    assert validate_port_or_unset(0) == ""
    assert validate_port_or_unset(80) == ""
    assert validate_port_or_unset(-1) != ""
    assert validate_port_or_unset(65536) != ""


@pytest.mark.parametrize("good", ["127.0.0.1", "0.0.0.0", "localhost", "my-host.example"])
def test_ipv4_host_accepts(good: str) -> None:
    assert validate_ipv4_host(good) == ""


@pytest.mark.parametrize("bad", ["::1", "999.1.1.1", "bad_host", "-x", "a" * 64, ""])
def test_ipv4_host_rejects(bad: str) -> None:
    assert validate_ipv4_host(bad) != ""


@pytest.mark.parametrize("good", ["::1", "ip6-localhost", "fe80::1"])
def test_ipv6_host_accepts(good: str) -> None:
    assert validate_ipv6_host(good) == ""


@pytest.mark.parametrize("bad", ["127.0.0.1", "bad host"])
def test_ipv6_host_rejects(bad: str) -> None:
    assert validate_ipv6_host(bad) != ""


def _capture(plugin_cls: Any, plugin_id: str, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    added: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    stub = MagicMock()
    stub.plugin_id = plugin_id
    monkeypatch.setattr(_proxy, "WINDOW_SIZE", MagicMock())

    def api(name: str) -> Any:
        if name == "plugins.core.settings:setting.add":
            return lambda *a, **k: added.append((a, k))
        if name == "plugins.core.settings:setting.get":
            return lambda _p, _s: 10
        return MagicMock()

    stub.api.side_effect = api
    plugin_cls._phook_initialize(stub)
    return added


@pytest.mark.parametrize(
    ("plugin_cls", "plugin_id", "names"),
    [
        (
            ProxyPlugin,
            "plugins.core.proxy",
            {
                "listenport",
                "mudport",
                "ipv4address",
                "ipv6address",
                "mudwindowsize",
                "linelen",
                "mudlinewait",
            },
        ),
        (CommandsPlugin, "plugins.core.commands", {"spamcount", "historysize", "command_indent"}),
        (EventsPlugin, "plugins.core.events", {"raised_history_size"}),
        (RecordPlugin, "plugins.debug.records", {"retained_trees", "tracking_max_changes"}),
    ],
)
def test_validated_defaults_pass_their_validators(
    plugin_cls: Any, plugin_id: str, names: set[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    added = _capture(plugin_cls, plugin_id, monkeypatch)
    seen = set()
    for args, kwargs in added:
        if args[1] in names:
            validator = kwargs.get("validator")
            assert validator is not None, args[1]
            assert validator(args[2]) == "", args[1]
            seen.add(args[1])
    assert seen == names
