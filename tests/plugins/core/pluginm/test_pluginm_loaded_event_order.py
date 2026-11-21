"""Tests for raising ev_<plugin_id>_loaded once, after ev_plugin_loaded (#663)."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins._baseplugin._base import Plugin
from bastproxy.plugins.core.pluginm.plugin._pluginm import PluginManager

LOADER = "libs.plugins.loader"
PM_ID = "plugins.core.pluginm"
PID = "plugins.test.sample"


class FakeEvents:
    """Records raises; callbacks for ev_<pid>_loaded register on ev_plugin_loaded."""

    def __init__(self, own_pids: list[str]) -> None:
        self.raised: list[str] = []
        self.own_pids = own_pids
        self.listeners: dict[str, list[Callable[[], None]]] = {}
        self.own_counts: dict[str, int] = dict.fromkeys(own_pids, 0)
        self.other_count = 0

    def add_listener(self, name: str, func: Callable[[], None]) -> None:
        self.listeners.setdefault(name, []).append(func)

    def raise_event(self, name: str, event_args: dict[str, Any] | None = None) -> None:
        self.raised.append(name)
        if name == "ev_plugin_loaded" and event_args:
            pid = event_args["plugin_id"]
            if pid in self.own_counts:
                self.add_listener(f"ev_{pid}_loaded", functools.partial(self._own, pid))
        for func in list(self.listeners.get(name, [])):
            func()

    def _own(self, pid: str) -> None:
        self.own_counts[pid] += 1

    def _other(self) -> None:
        self.other_count += 1


def _fake(pids: list[str]) -> FakeEvents:
    fake = FakeEvents(pids)
    for pid in pids:
        fake.add_listener(f"ev_{pid}_loaded", fake._other)
    return fake


def _base_stub(fake: FakeEvents, *, startup: bool) -> MagicMock:
    def api(name: str) -> Any:
        if name == "plugins.core.events:event.raise":
            return fake.raise_event
        if name == "plugins.core.proxy:mud.is.connected":
            return lambda: False
        return MagicMock()

    stub = MagicMock()
    stub.plugin_id = PID
    stub.api = MagicMock(side_effect=api)
    stub.api.startup = startup
    return stub


def _load_command_stub(fake: FakeEvents) -> MagicMock:
    funcs: dict[str, Any] = {
        "plugins.core.commands:command.current.args.get": lambda: {"plugin": PID},
        f"{LOADER}:plugin.is.loaded": lambda _pid: False,
        f"{LOADER}:plugin.list.not.loaded": lambda: [PID],
        f"{LOADER}:plugin.load": lambda _pids: {"loaded_plugins": [PID], "bad_plugins": []},
        "plugins.core.settings:setting.get": lambda *_a: [],
        "plugins.core.settings:setting.set": MagicMock(),
        "plugins.core.events:event.raise": fake.raise_event,
    }
    stub = MagicMock()
    stub.plugin_id = PM_ID
    stub.api = lambda name: funcs[name]
    return stub


def test_base_hook_raises_plugin_loaded_first_and_each_listener_sees_it_once() -> None:
    fake = _fake([PID])
    Plugin._phook_base_post_initialize_setup(_base_stub(fake, startup=False))
    assert fake.raised == ["ev_plugin_loaded", f"ev_{PID}_loaded"]
    assert fake.own_counts[PID] == 1
    assert fake.other_count == 1


def test_base_hook_at_startup_raises_nothing() -> None:
    fake = _fake([PID])
    Plugin._phook_base_post_initialize_setup(_base_stub(fake, startup=True))
    assert fake.raised == []


def test_load_command_raises_no_events() -> None:
    fake = _fake([PID])
    result = PluginManager._command_load(_load_command_stub(fake))
    assert result.success
    assert fake.raised == []


def test_full_load_counts_each_listener_once() -> None:
    fake = _fake([PID])
    Plugin._phook_base_post_initialize_setup(_base_stub(fake, startup=False))
    PluginManager._command_load(_load_command_stub(fake))
    assert fake.own_counts[PID] == 1
    assert fake.other_count == 1


def test_startup_raises_plugin_loaded_before_own_loaded_for_each_plugin() -> None:
    pids = ["plugins.a", "plugins.b"]
    fake = _fake(pids)
    funcs: dict[str, Any] = {
        f"{LOADER}:plugin.list.loaded": lambda: pids,
        "plugins.core.events:event.raise": fake.raise_event,
        f"{PM_ID}:plugin.state.save.all": MagicMock(),
        "plugins.core.timers:timer.add": MagicMock(),
    }
    stub = MagicMock()
    stub.plugin_id = PM_ID
    stub.api = lambda name: funcs[name]
    PluginManager._eventcb_all_events_registered(stub)
    assert fake.raised == [
        "ev_plugin_loaded",
        "ev_plugin_loaded",
        "ev_plugins.a_loaded",
        "ev_plugins.b_loaded",
    ]
    assert fake.own_counts == {"plugins.a": 1, "plugins.b": 1}


def test_startup_later_plugin_listener_sees_earlier_plugins_loaded_event_once() -> None:
    pids = ["plugins.a", "plugins.b"]
    fake = FakeEvents(pids)
    seen = 0

    def b_listener() -> None:
        nonlocal seen
        seen += 1

    original = fake.raise_event

    def raise_event(name: str, event_args: dict[str, Any] | None = None) -> None:
        original(name, event_args)
        if name == "ev_plugin_loaded" and event_args and event_args["plugin_id"] == "plugins.b":
            fake.add_listener("ev_plugins.a_loaded", b_listener)

    funcs: dict[str, Any] = {
        f"{LOADER}:plugin.list.loaded": lambda: pids,
        "plugins.core.events:event.raise": raise_event,
        f"{PM_ID}:plugin.state.save.all": MagicMock(),
        "plugins.core.timers:timer.add": MagicMock(),
    }
    stub = MagicMock()
    stub.plugin_id = PM_ID
    stub.api = lambda name: funcs[name]
    PluginManager._eventcb_all_events_registered(stub)
    assert seen == 1
