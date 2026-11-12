"""Shared fixture: a stand-in plugin whose trigger methods are the real ones."""

# Standard Library
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# Third Party
import pytest

# Project
from bastproxy.libs.records.enums import Originated
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.colors.plugin._colors import ColorsPlugin
from bastproxy.plugins.core.triggers.plugin import _triggers
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin

OWNER = "plugins.test.owner"
PLUGIN = "plugins.core.triggers"
RED_ANSI = "\x1b[31m"
RESET_ANSI = "\x1b[0m"


class Harness:
    """A stand-in plugin: real ``TriggersPlugin`` methods on a plain object."""

    plugin_id = PLUGIN

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.raised: list[tuple[str, dict[str, Any]]] = []
        self.logged: list[tuple[Any, ...]] = []
        self.listeners: set[str] = set()
        self.callbacks: dict[str, Callable[[], None]] = {}
        self.line: Any = None
        self.current_record: Any = None
        self.command_args: dict[str, Any] = {}

        def event_raise(event_name: str, event_args: dict[str, Any]) -> dict[str, Any]:
            self.raised.append((event_name, dict(event_args)))
            if callback := self.callbacks.get(event_args["trigger_name"]):
                callback()
            return event_args

        monkeypatch.setattr(_triggers, "API", lambda owner_id: lambda _name: event_raise)
        monkeypatch.setattr(_triggers, "log_to", lambda *a, **k: self.logged.append(a))
        # state comes from the real init hook
        TriggersPlugin._phook_init_plugin(self)
        for name in ("beall", "all", "emptyline"):
            self.add(name, None, owner_id=PLUGIN, enabled=False)

    create_trigger_id = staticmethod(TriggersPlugin.create_trigger_id)

    def __getattr__(self, name: str) -> Any:
        method = getattr(TriggersPlugin, name)
        return lambda *a, **k: method(self, *a, **k)

    def api(self, name: str) -> Callable[..., Any]:
        """Dispatch the API names the trigger methods use."""
        if name == "libs.api:caller.owner.get":
            return lambda **_kw: OWNER
        if name == "plugins.core.events:event.current.record.get":
            return lambda: self.current_record
        if name == "plugins.core.events:event.get":
            return lambda event_name: SimpleNamespace(
                isempty=lambda: event_name not in self.listeners
            )
        if name == "plugins.core.events:event.exists":
            return lambda _event_name: False
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: self.command_args
        prefix = f"{PLUGIN}:"
        if name.startswith(prefix):
            method = getattr(TriggersPlugin, "_api_" + name[len(prefix) :].replace(".", "_"))
            return lambda *a, **k: method(self, *a, **k)
        raise KeyError(name)

    def add(self, name: str, regex: str | None, owner_id: str = OWNER, **kwargs: Any) -> Any:
        """Add a trigger through the real ``trigger.add``."""
        return TriggersPlugin._api_trigger_add(self, name, regex, owner_id, **kwargs)

    def item(self, name: str, owner_id: str = OWNER) -> Any:
        """Return the TriggerItem for a name."""
        return self.triggers[self.create_trigger_id(name, owner_id)]

    def listen(self, name: str, owner_id: str = OWNER) -> None:
        """Pretend a function is registered to the trigger's event."""
        self.listeners.add(self.item(name, owner_id).event_name)

    def ordered_names(self) -> list[str]:
        """Names of the triggers in the matching list, in matching order."""
        return [item.trigger_name for item in self._ordered]

    def send(self, text: str, *, ansi: str | None = None, internal: bool = False) -> list[str]:
        """Send one MUD line through the real path; return trigger names raised."""
        self.line = NetworkDataLine(
            ansi if ansi is not None else text,
            originated=Originated.INTERNAL if internal else Originated.MUD,
        )
        self.current_record = {"line": self.line}
        before = len(self.raised)
        self._eventcb_check_trigger()
        return [args["trigger_name"] for _event_name, args in self.raised[before:]]

    def errors(self) -> list[tuple[Any, ...]]:
        """Logged calls at ERROR level."""
        return [call for call in self.logged if len(call) > 1 and call[1] == logging.ERROR]


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Harness:
    colors = MagicMock()
    colors.plugin_id = "plugins.core.colors"
    table = {
        "plugins.core.colors:ansicode.strip": lambda text: ColorsPlugin._api_ansicode_strip(
            colors, text
        ),
        "plugins.core.colors:ansicode.to.colorcode": lambda text: (
            ColorsPlugin._api_ansicode_to_colorcode(colors, text)
        ),
    }
    monkeypatch.setattr(NetworkDataLine, "api", staticmethod(lambda name: table[name]))
    return Harness(monkeypatch)
