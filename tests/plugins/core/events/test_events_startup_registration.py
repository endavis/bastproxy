"""Decorated handlers register for plugins loaded during startup (#585)."""

# Standard Library
from typing import Any

# Project
from bastproxy.plugins.core.events.plugin._events import EventsPlugin

PLUGIN_ID = "plugins.test585.late"


class _Api:
    """Stand-in for the plugin api: a startup flag and a callable returning the record."""

    def __init__(self, startup: bool) -> None:
        self.startup = startup

    def __call__(self, _name: str) -> Any:
        return lambda: {"plugin_id": PLUGIN_ID}


class _Stub:
    """Just enough of EventsPlugin to run the ev_plugin_loaded callback."""

    plugin_id = "plugins.core.events"

    def __init__(self, *, startup: bool, done: bool) -> None:
        self.api = _Api(startup)
        self._startup_registration_done = done
        self.registered: list[str] = []

    def _register_events_for_plugin(self, plugin_id: str) -> None:
        self.registered.append(plugin_id)


def _plugin_loaded(stub: _Stub) -> None:
    EventsPlugin._eventcb_plugin_initialized(stub)


def test_load_before_post_startup_defers() -> None:
    stub = _Stub(startup=True, done=False)
    _plugin_loaded(stub)
    assert stub.registered == []


def test_load_after_post_startup_during_startup_registers() -> None:
    stub = _Stub(startup=True, done=True)
    _plugin_loaded(stub)
    assert stub.registered == [PLUGIN_ID]


def test_load_after_startup_registers() -> None:
    stub = _Stub(startup=False, done=False)
    _plugin_loaded(stub)
    assert stub.registered == [PLUGIN_ID]


def test_post_startup_callback_sets_flag_before_raising() -> None:
    calls: list[str] = []

    class _S:
        plugin_id = "plugins.core.events"
        _startup_registration_done = False

        def _register_all_plugin_events(self) -> None:
            calls.append("register")

        def api(self, _name: str) -> Any:
            return lambda _ev: calls.append(f"raise:{self._startup_registration_done}")

    s = _S()
    EventsPlugin._eventcb_post_startup_plugins_loaded(s)  # type: ignore[arg-type]
    assert s._startup_registration_done is True
    assert calls == ["register", "raise:True"]
