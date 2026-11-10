"""Shared fixtures for the record tests: stand-in plugin APIs (#239)."""

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
class EventCall:
    """One call to the event.raise stand-in."""

    name: str
    kwargs: dict[str, Any]
    snapshot: list[Any]


@dataclass
class StandIns:
    """Calls the stand-in plugin APIs received, plus the settings they answer with."""

    events: list[EventCall] = field(default_factory=list)
    sent_to_clients: list[tuple[str, Any]] = field(default_factory=list)
    api_calls: list[str] = field(default_factory=list)
    logged_in: set[str] = field(default_factory=set)
    view_clients: set[str] = field(default_factory=set)
    clients: list[str] = field(default_factory=list)
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
        data_list = kwargs.get("data_list", [])
        holder.api_calls.append("event.raise")
        holder.events.append(EventCall(event_name, kwargs, [item.line for item in data_list]))
        if holder.hook is not None and event_name.endswith("modify"):
            holder.hook(event_name, data_list)

    def client_list(uuid_only: bool = False) -> list[str]:
        holder.api_calls.append("client.list")
        return list(holder.clients)

    def is_view_client(uuid: str) -> bool:
        return uuid in holder.view_clients

    def is_logged_in(uuid: str) -> bool:
        return uuid in holder.logged_in

    def client_send(uuid: str, line: Any) -> None:
        holder.sent_to_clients.append((uuid, line.line))

    def mud_connection_get() -> FakeConnection | None:
        return holder.connection

    def preamble_get() -> str:
        holder.api_calls.append("preamble.get")
        return "#BP"

    def preamble_color_get(error: bool = False) -> str:
        holder.api_calls.append("preamble.color.get")
        return "@R" if error else "@C"

    def to_ansicode(text: str) -> str:
        return f"ANSI({text})"

    def id_is_valid(_plugin_id: str) -> bool:
        return False

    stand_ins: dict[str, Callable[..., Any]] = {
        "plugins.core.events:event.raise": event_raise,
        "plugins.core.clients:client.list": client_list,
        "plugins.core.clients:client.is.view.client": is_view_client,
        "plugins.core.clients:client.is.logged.in": is_logged_in,
        "plugins.core.clients:client.send": client_send,
        "plugins.core.proxy:mud.connection.get": mud_connection_get,
        "plugins.core.proxy:preamble.get": preamble_get,
        "plugins.core.proxy:preamble.color.get": preamble_color_get,
        "plugins.core.colors:colorcode.to.ansicode": to_ansicode,
        "libs.plugins.loader:plugin.id.is.valid": id_is_valid,
    }
    saved = {name: API._class_api.get(name) for name in stand_ins}
    api = API("test239")
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
