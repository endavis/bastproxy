"""Tests for watch.add and watch.remove results and the regex lookup (#670)."""

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.plugins.core.watch.plugin._watch import WatchPlugin

PID = "plugins.test.a"


class _Stub:
    """Plugin stand-in with real containers and a recording api."""

    plugin_id = "plugins.core.watch"

    def __init__(self) -> None:
        self.regex_lookup: dict[str, str] = {}
        self.watch_data: dict[str, Any] = {}
        self.registered: set[str] = set()
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.caller_owner: str | None = PID

    def api(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            if name == "libs.api:caller.owner.get":
                return self.caller_owner
            if name == "plugins.core.events:event.has.registrations":
                return args[0] in self.registered
            return None

        return call

    def called(self, name: str) -> list[tuple[Any, ...]]:
        return [a for n, a, _k in self.calls if n == name]


def _add(stub: _Stub, name: str, regex: str, owner: str | None = PID) -> bool:
    return bool(WatchPlugin._api_watch_add(stub, name, regex, owner))


def _remove(stub: _Stub, name: str, force: bool = False) -> bool:
    return bool(WatchPlugin._api_watch_remove(stub, name, force))


@pytest.fixture
def stub() -> _Stub:
    return _Stub()


def test_add_returns_true(stub: _Stub) -> None:
    assert _add(stub, "lcw", "^lcfoo") is True
    assert stub.regex_lookup == {"^lcfoo": "lcw"}
    assert "lcw" in stub.watch_data


def test_readd_frees_old_regex(stub: _Stub) -> None:
    assert _add(stub, "lcw", "^lcfoo")
    assert _add(stub, "lcw", "^lcbar")
    assert stub.regex_lookup == {"^lcbar": "lcw"}
    assert _add(stub, "lcw2", "^lcfoo") is True
    assert stub.regex_lookup == {"^lcbar": "lcw", "^lcfoo": "lcw2"}


def test_readd_same_name_same_regex_is_replace(stub: _Stub) -> None:
    assert _add(stub, "lcw", "^lcfoo")
    assert _add(stub, "lcw", "^lcfoo") is True
    assert stub.regex_lookup == {"^lcfoo": "lcw"}


def test_duplicate_regex_is_refused_with_warning(
    stub: _Stub, caplog: pytest.LogCaptureFixture
) -> None:
    assert _add(stub, "lcw", "^lcfoo")
    with caplog.at_level(logging.WARNING):
        assert _add(stub, "lcw2", "^lcfoo") is False
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert stub.regex_lookup == {"^lcfoo": "lcw"}
    assert "lcw2" not in stub.watch_data


def test_invalid_regex_returns_false_and_keeps_old_watch(stub: _Stub) -> None:
    assert _add(stub, "lcw", "^lcfoo")
    assert _add(stub, "lcw", "(") is False
    assert stub.regex_lookup == {"^lcfoo": "lcw"}
    assert stub.watch_data["lcw"].regex == "^lcfoo"


def test_missing_owner_returns_false(stub: _Stub) -> None:
    stub.caller_owner = None
    assert _add(stub, "lcw", "^lcfoo", owner=None) is False
    assert stub.watch_data == {}


def test_remove_missing_watch_is_false(stub: _Stub) -> None:
    assert _remove(stub, "nosuch") is False


def test_remove_with_registrations_needs_force(stub: _Stub) -> None:
    _add(stub, "lcw", "^lcfoo")
    stub.registered.add("watch_lcw")
    assert _remove(stub, "lcw") is False
    assert "lcw" in stub.watch_data
    assert _remove(stub, "lcw", force=True) is True
    assert stub.watch_data == {}
    assert stub.regex_lookup == {}


def test_remove_clears_maps_and_event_without_event_get(stub: _Stub) -> None:
    _add(stub, "lcw", "^lcfoo")
    assert _remove(stub, "lcw") is True
    assert stub.watch_data == {}
    assert stub.regex_lookup == {}
    assert stub.called("plugins.core.events:event.remove") == [("watch_lcw",)]
    assert stub.called("plugins.core.events:event.get") == []


def test_remove_for_plugin_removes_only_owners_watches() -> None:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.watch"
    real = _Stub()
    _add(real, "a1", "^a1", owner="plugins.test.a")
    _add(real, "b1", "^b1", owner="plugins.test.b")
    stub.watch_data = real.watch_data
    stub.api = lambda name: lambda n: _remove(real, n)
    WatchPlugin._api_watch_remove_for_plugin(stub, "plugins.test.a")
    assert list(real.watch_data) == ["b1"]
