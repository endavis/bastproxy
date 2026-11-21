"""Local stand-ins for the input path tests (copied from tests/libs/records/conftest.py)."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from bastproxy.libs.api import API

SPLIT_REGEX = r"(?<=[^\|])\|(?=[^\|])"


class FakeConnection:
    """A stand-in mud connection that records what it is sent."""

    def __init__(self) -> None:
        self.sent: list[Any] = []

    def send_to(self, line: Any) -> None:
        self.sent.append(line)


@dataclass
class StandIns:
    """What the stand-in plugin APIs saw, and the hook run for each modify event."""

    events: list[dict[str, Any]] = field(default_factory=list)
    connection: FakeConnection | None = None
    hook: Callable[[str, list[Any]], None] | None = None


@pytest.fixture
def split_regex(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the API the command split regex the proxy plugin sets at startup."""
    monkeypatch.setattr(API, "command_split_regex", SPLIT_REGEX)


@pytest.fixture
def plugin_stand_ins() -> Iterator[StandIns]:
    """Register stand-ins for the plugin APIs the record types call, then restore."""
    holder = StandIns()

    def event_raise(event_name: str, **kwargs: Any) -> None:
        holder.events.append(kwargs)
        if holder.hook is not None and event_name.endswith("modify"):
            holder.hook(event_name, kwargs.get("data_list", []))

    stand_ins: dict[str, Callable[..., Any]] = {
        "plugins.core.events:event.raise": event_raise,
        "plugins.core.clients:client.list": lambda uuid_only=False: [],
        "plugins.core.clients:client.is.view.client": lambda uuid: False,
        "plugins.core.clients:client.is.logged.in": lambda uuid: False,
        "plugins.core.clients:client.send": lambda uuid, line: None,
        "plugins.core.proxy:mud.connection.get": lambda: holder.connection,
        "plugins.core.proxy:preamble.get": lambda: "#BP",
        "plugins.core.proxy:preamble.color.get": lambda error=False: "@R" if error else "@C",
        "plugins.core.colors:colorcode.to.ansicode": lambda text: f"ANSI({text})",
        "libs.plugins.loader:plugin.id.is.valid": lambda _plugin_id: False,
    }
    saved = {name: API._class_api.get(name) for name in stand_ins}
    api = API("test711")
    for full_name, func in stand_ins.items():
        top, name = full_name.split(":")
        api.add(top, name, func, force=True, description="stand-in")
    try:
        yield holder
    finally:
        for full_name, item in saved.items():
            if item is None:
                API._class_api.pop(full_name, None)
            else:
                API._class_api[full_name] = item
