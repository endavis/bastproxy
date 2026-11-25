"""Tests for watch matching on stripped input and callbacks rewriting the line (#775, #785)."""

import re
from collections.abc import Callable
from typing import Any

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.client.aliases.plugin._aliases import ALIAS_PRIORITY
from bastproxy.plugins.core.watch.plugin._watch import WATCH_PRIORITY, WatchItem, WatchPlugin

Callback = Callable[[dict[str, Any]], None]


class _Record(dict[str, Any]):
    """Event record stand-in that remembers its `addupdate` calls."""

    def __init__(self, line: NetworkDataLine) -> None:
        super().__init__(line=line)
        self.updates: list[str] = []

    def addupdate(self, flag: Any, msg: str, savedata: bool = True) -> None:
        """Remember the update message."""
        self.updates.append(msg)


class _Stub:
    """Plugin stand-in: real containers, `event.raise` routed to per-event callbacks."""

    plugin_id = "plugins.core.watch"

    def __init__(self, line: NetworkDataLine) -> None:
        self.record = _Record(line)
        self.watch_data: dict[str, WatchItem] = {}
        self.callbacks: dict[str, Callback] = {}
        self.raised: list[dict[str, Any]] = []

    def add(self, name: str, regex: str, callback: Callback | None = None) -> None:
        """Register a watch and an optional callback."""
        self.watch_data[name] = WatchItem(
            name=name,
            regex=regex,
            owner="plugins.x",
            event_name=f"ev_{name}",
            compiled=re.compile(regex),
        )
        if callback:
            self.callbacks[f"ev_{name}"] = callback

    def api(self, name: str) -> Any:
        """Return the stand-in for an API call."""
        if name == "plugins.core.events:event.current.record.get":
            return lambda: self.record
        if name == "plugins.core.events:event.raise":
            return self._raise
        raise AssertionError(name)

    def _raise(self, event_name: str, event_args: dict[str, Any]) -> None:
        self.raised.append(event_args)
        if callback := self.callbacks.get(event_name):
            callback(event_args)

    def run(self) -> None:
        """Run the callback under test."""
        WatchPlugin._eventcb_check_command(self)


def _stub(text: str) -> _Stub:
    return _Stub(NetworkDataLine(text, originated="client"))


def test_trailing_space_matches_anchored_watch() -> None:
    """`^superhero loud$` fires on input with a trailing space."""
    stub = _stub("superhero loud ")
    stub.add("sh", r"^superhero loud$")
    stub.run()
    assert stub.watch_data["sh"].hits == 1
    assert len(stub.raised) == 1


def test_leading_spaces_match_anchored_watch() -> None:
    """`^superhero loud$` fires on input with leading spaces."""
    stub = _stub("  superhero loud")
    stub.add("sh", r"^superhero loud$")
    stub.run()
    assert stub.watch_data["sh"].hits == 1
    assert len(stub.raised) == 1


def test_data_and_matched_come_from_stripped_text() -> None:
    """The callback's `data` and `matched` use the stripped text."""
    stub = _stub("say hi  ")
    stub.add("say", r"^say (?P<what>\w+)$")
    stub.run()
    assert stub.raised[0]["data"] == "say hi"
    assert stub.raised[0]["matched"] == {"what": "hi"}


def test_matching_alone_leaves_the_line_unchanged() -> None:
    """Without a callback edit, the sent text keeps its whitespace and `send` stays True."""
    stub = _stub("  superhero loud ")
    stub.add("sh", r"^superhero loud$")
    stub.run()
    line = stub.record["line"]
    assert line.line == "  superhero loud "
    assert line.send is True
    assert stub.record.updates == []


def test_args_carry_the_record_line() -> None:
    """The `line` arg is the record's line object."""
    stub = _stub("look")
    stub.add("look", r"^look$")
    stub.run()
    assert stub.raised[0]["line"] is stub.record["line"]


def test_callback_rewrites_line() -> None:
    """Setting `args["line"].line` rewrites the line and records a MODIFY update."""

    def cb(args: dict[str, Any]) -> None:
        args["line"].line = "superhero quiet"

    stub = _stub("superhero loud")
    stub.add("sh", r"^superhero loud$", cb)
    stub.run()
    assert stub.record["line"].line == "superhero quiet"
    assert stub.record["line"].send is True
    assert stub.record.updates == ["watch sh rewrote the line"]


def test_callback_stops_line() -> None:
    """Setting `args["line"].send = False` stops the line and records a MODIFY update."""

    def cb(args: dict[str, Any]) -> None:
        args["line"].send = False

    stub = _stub("superhero loud")
    stub.add("sh", r"^superhero loud$", cb)
    stub.run()
    assert stub.record["line"].send is False
    assert stub.record.updates == ["watch sh stopped the line"]


def test_callback_without_changes_records_nothing() -> None:
    """A callback that changes nothing records no update."""
    stub = _stub("superhero loud")
    stub.add("sh", r"^superhero loud$", lambda args: None)
    stub.run()
    assert stub.record.updates == []


def test_two_watches_both_fire_last_writer_wins() -> None:
    """Both watches match the original stripped text; the second sees the first's rewrite."""
    seen: list[str] = []

    def first(args: dict[str, Any]) -> None:
        seen.append(args["data"])
        args["line"].line = "one"

    def second(args: dict[str, Any]) -> None:
        seen.append(args["data"])
        seen.append(args["line"].line)
        args["line"].line = "two"

    stub = _stub("go north")
    stub.add("a", r"^go", first)
    stub.add("b", r".*north$", second)
    stub.run()
    assert seen == ["go north", "go north", "one"]
    assert stub.record["line"].line == "two"
    assert stub.watch_data["a"].hits == stub.watch_data["b"].hits == 1


def test_callback_can_remove_a_watch_during_the_loop() -> None:
    """Removing a watch from a callback does not break the iteration."""
    stub = _stub("go")

    def cb(args: dict[str, Any]) -> None:
        del stub.watch_data["b"]

    stub.add("a", r"^go$", cb)
    stub.add("b", r"^go$")
    stub.run()
    assert "b" not in stub.watch_data
    assert stub.watch_data["a"].hits == 1


def test_callback_priority_between_commands_and_aliases() -> None:
    """The callback registers at WATCH_PRIORITY: after commands (50), before aliases (55)."""
    args = WatchPlugin._eventcb_check_command.event_registration
    assert args == [{"event_name": "ev_to_mud_data_modify", "priority": WATCH_PRIORITY}]
    assert 50 < WATCH_PRIORITY < ALIAS_PRIORITY


def test_watch_add_describes_line_arg() -> None:
    """`watch.add` passes `line` in `arg_descriptions` to `event.add`."""
    calls: list[dict[str, Any]] = []

    class _AddStub:
        plugin_id = "plugins.core.watch"

        def __init__(self) -> None:
            self.regex_lookup: dict[str, str] = {}
            self.watch_data: dict[str, Any] = {}

        def api(self, name: str) -> Any:
            def call(*a: Any, **kw: Any) -> Any:
                if name == "plugins.core.events:event.add":
                    calls.append(kw)
                return None

            return call

    stub = _AddStub()
    assert WatchPlugin._api_watch_add(stub, "w", r"^x$", owner="plugins.x")
    assert "line" in calls[0]["arg_descriptions"]
