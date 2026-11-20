"""Tests for adding a timer under a name that is already in use (#628)."""

import datetime
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin

FIRE = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
SLOT = int(FIRE.timestamp())


def _timer(name: str, owner: str = "plugins.test.a", func: Callable[[], None] | None = None) -> Any:
    timer = SimpleNamespace(
        name=name,
        owner_id=owner,
        enabled=True,
        onetime=False,
        log=False,
        next_fire_datetime=FIRE,
    )
    timer.get_next_fire = lambda: FIRE + datetime.timedelta(seconds=5)
    timer.execute = func or (lambda: None)
    return timer


def _stub(new_timers: list[Any]) -> Any:
    stub = MagicMock()
    stub.plugin_id = "plugins.core.timers"
    stub.timer_events = {}
    stub.timer_lookup = {}
    stub.overall_fire_count = 0
    stub._add_timer_internal = lambda t: TimersPlugin._add_timer_internal(stub, t)
    stub._remove_timer_internal = lambda t: TimersPlugin._remove_timer_internal(stub, t)
    stub._api_timer_add = lambda *a, **k: TimersPlugin._api_timer_add(stub, *a, **k)
    stub._api_timer_remove = lambda n: TimersPlugin._api_timer_remove(stub, n)
    stub._api_timer_remove_for_plugin = lambda n: TimersPlugin._api_timer_remove_for_plugin(stub, n)

    def api(name: str) -> Callable[..., Any]:
        if name == "libs.api:caller.owner.get":
            return lambda **_k: "plugins.test.a"
        if name == "libs.plugins.loader:plugin.id.is.valid":
            return lambda _p: True
        if name.endswith("timer.remove"):
            return cast("Callable[..., Any]", stub._api_timer_remove)
        raise KeyError(name)

    stub.api = api
    return stub


def _patch_timer(monkeypatch: Any, created: list[Any]) -> None:
    def factory(name: str, func: Any, _seconds: float, owner: str, **_kw: Any) -> Any:
        timer = _timer(name, owner, func)
        created.append(timer)
        return timer

    monkeypatch.setattr("bastproxy.plugins.core.timers.plugin._timers.Timer", factory)


def _scheduled(stub: Any) -> list[Any]:
    return [t for slot in stub.timer_events.values() for t in slot]


def test_duplicate_add_replaces_and_leaves_one_timer(monkeypatch: Any) -> None:
    created: list[Any] = []
    _patch_timer(monkeypatch, created)
    stub = _stub(created)
    stub._api_timer_add("t", lambda: None, 5)
    stub._api_timer_add("t", lambda: None, 5)

    assert len(created) == 2
    assert _scheduled(stub) == [created[1]]
    assert stub.timer_lookup["t"] is created[1]

    stub._api_timer_remove("t")
    assert _scheduled(stub) == []
    assert stub.timer_lookup == {}


def test_unique_add_refuses_and_keeps_old_timer(monkeypatch: Any) -> None:
    created: list[Any] = []
    _patch_timer(monkeypatch, created)
    stub = _stub(created)
    stub._api_timer_add("t", lambda: None, 5)

    assert stub._api_timer_add("t", lambda: None, 5, unique=True) is None

    assert len(created) == 1
    assert _scheduled(stub) == [created[0]]
    assert stub.timer_lookup["t"] is created[0]


def test_remove_for_plugin_after_replacement(monkeypatch: Any) -> None:
    created: list[Any] = []
    _patch_timer(monkeypatch, created)
    stub = _stub(created)
    stub._api_timer_add("t", lambda: None, 5)
    stub._api_timer_add("t", lambda: None, 5)
    stub._api_timer_add("u", lambda: None, 5)

    stub._api_timer_remove_for_plugin("plugins.test.a")

    assert _scheduled(stub) == []
    assert stub.timer_lookup == {}


def test_add_timer_internal_unschedules_the_timer_it_displaces() -> None:
    stub = _stub([])
    old = _timer("t")
    new = _timer("t")
    stub._add_timer_internal(old)
    stub._add_timer_internal(new)

    assert _scheduled(stub) == [new]
    assert stub.timer_lookup["t"] is new


def test_timer_readding_itself_while_firing_keeps_new_and_drops_old() -> None:
    stub = _stub([])
    new = _timer("t")
    old = _timer("t")
    old.execute = lambda: stub._add_timer_internal(new)
    stub._add_timer_internal(old)

    TimersPlugin.execute_timer(stub, SLOT, old)

    assert stub.timer_lookup["t"] is new
    assert _scheduled(stub) == [new]
    assert SLOT + 5 not in stub.timer_events
