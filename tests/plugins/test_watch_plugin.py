# Project: bastproxy
# Filename: tests/plugins/test_watch_plugin.py
#
# File Description: Tests for the watch plugin's client input matching
#
# By: Bast
"""Unit tests for `WatchPlugin._eventcb_check_command`.

Issue #55: the callback passed the `NetworkDataLine` record to `re.match`
instead of its text, so a registered watch never fired.

"""

import re
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.core.watch.plugin._watch import WatchItem, WatchPlugin


def _item(
    name: str = "sayw",
    regex: str = r"^say (?P<what>\w+)",
    owner: str = "plugins.x",
    event_name: str | None = None,
    hits: int = 0,
) -> WatchItem:
    """Build a `WatchItem` with its regex compiled."""
    return WatchItem(
        name=name,
        regex=regex,
        owner=owner,
        event_name=event_name or f"watch_{name}",
        compiled=re.compile(regex),
        hits=hits,
    )


def _run(line: NetworkDataLine, regex: str = r"^say (?P<what>\w+)") -> tuple[Any, MagicMock]:
    """Run the callback against `line` with one watch registered.

    Returns the stub plugin and the `event.raise` mock.
    """
    raise_event = MagicMock()

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.current.record.get":
            return lambda: {"line": line}
        if name == "plugins.core.events:event.raise":
            return raise_event
        raise AssertionError(name)

    stub = MagicMock()
    stub.plugin_id = "plugins.core.watch"
    stub.api = api
    stub.watch_data = {"sayw": _item(regex=regex, event_name="ev_watch_sayw")}
    WatchPlugin._eventcb_check_command(stub)
    return stub, raise_event


def test_matching_line_raises_event_with_text() -> None:
    """A matching client line raises the watch event with text, not the record."""
    stub, raise_event = _run(NetworkDataLine("say hi", originated="client"))

    assert stub.watch_data["sayw"].hits == 1
    raise_event.assert_called_once()
    assert raise_event.call_args.args == ("ev_watch_sayw",)
    match_args = raise_event.call_args.kwargs["event_args"]
    assert match_args["data"] == "say hi"
    assert isinstance(match_args["data"], str)
    assert match_args["matched"] == {"what": "hi"}
    assert match_args["cmdname"] == "cmd_sayw"


def test_non_matching_line_does_not_fire() -> None:
    """A line that does not match leaves hits at zero and raises nothing."""
    stub, raise_event = _run(NetworkDataLine("look", originated="client"))

    assert stub.watch_data["sayw"].hits == 0
    raise_event.assert_not_called()


def test_telnet_command_line_is_skipped() -> None:
    """A COMMAND-TELNET line is not matched even if its text would match."""
    stub, raise_event = _run(
        NetworkDataLine("say hi", originated="client", line_type="COMMAND-TELNET"),
        regex=r"^say",
    )

    assert stub.watch_data["sayw"].hits == 0
    raise_event.assert_not_called()


def test_remove_all_data_for_plugin_removes_every_owned_watch() -> None:
    """Issue #123: removing watches must not mutate the dict being iterated."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.watch"
    stub.watch_data = {
        "a": _item("a", owner="plugins.x"),
        "b": _item("b", owner="plugins.x"),
        "c": _item("c", owner="plugins.x"),
        "d": _item("d", owner="plugins.other"),
    }

    def remove(name: str) -> None:
        del stub.watch_data[name]

    def api(name: str) -> Any:
        if name == "plugins.core.watch:watch.remove":
            return remove
        raise AssertionError(name)

    stub.api = api
    WatchPlugin._api_watch_remove_for_plugin(stub, "plugins.x")
    assert list(stub.watch_data) == ["d"]


def _plugin(
    api_map: dict[str, Any] | None = None,
) -> Any:
    """Return a stub plugin with empty watch state and a dispatching `api`."""
    stub = MagicMock()
    stub.plugin_id = "plugins.core.watch"
    stub.watch_data = {}
    stub.regex_lookup = {}
    api_map = api_map or {}

    def api(name: str) -> Any:
        if name in api_map:
            return api_map[name]
        raise AssertionError(name)

    stub.api = api
    return stub


def test_watch_item_defaults_and_slots() -> None:
    """Defaults are zero hits and a per-instance extra dict; no __dict__."""
    one, two = _item("a"), _item("b")
    assert one.hits == 0
    assert one.extra == {}
    one.extra["k"] = 1
    assert two.extra == {}
    assert not hasattr(one, "__dict__")
    with pytest.raises(AttributeError):
        one.bogus = 1  # type: ignore[attr-defined]


def test_watch_add_stores_item_and_adds_event() -> None:
    """watch.add stores a WatchItem, the regex lookup and the event."""
    event_add = MagicMock()
    stub = _plugin({"plugins.core.events:event.add": event_add})
    WatchPlugin._api_watch_add(stub, "w", r"^go", owner="plugins.x", color="red")

    item = stub.watch_data["w"]
    assert isinstance(item, WatchItem)
    assert (item.name, item.regex, item.owner) == ("w", r"^go", "plugins.x")
    assert item.event_name == "watch_w"
    assert item.hits == 0
    assert item.compiled.match("go north")
    assert item.extra == {"color": "red"}
    assert stub.regex_lookup == {r"^go": "w"}
    assert event_add.call_args.args == ("watch_w", "plugins.x")


def test_watch_add_duplicate_regex_stores_nothing_new() -> None:
    """A regex that is already registered is not added again."""
    event_add = MagicMock()
    stub = _plugin({"plugins.core.events:event.add": event_add})
    WatchPlugin._api_watch_add(stub, "w", r"^go", owner="plugins.x")
    event_add.reset_mock()
    WatchPlugin._api_watch_add(stub, "w2", r"^go", owner="plugins.x")

    assert list(stub.watch_data) == ["w"]
    event_add.assert_not_called()


def test_watch_add_bad_regex_stores_nothing() -> None:
    """Bug 2: an invalid regex leaves no half-built watch and no event."""
    event_add = MagicMock()
    stub = _plugin({"plugins.core.events:event.add": event_add})
    WatchPlugin._api_watch_add(stub, "bad", "(", owner="plugins.x")

    assert stub.watch_data == {}
    assert stub.regex_lookup == {}
    event_add.assert_not_called()


def test_watch_remove_deletes_when_event_empty() -> None:
    """watch.remove deletes the item and its regex lookup."""
    event = MagicMock()
    event.isempty.return_value = True
    stub = _plugin({"plugins.core.events:event.get": lambda _name: event})
    stub.watch_data["w"] = _item("w", regex=r"^go")
    stub.regex_lookup[r"^go"] = "w"

    assert WatchPlugin._api_watch_remove(stub, "w") is None
    assert stub.watch_data == {}
    assert stub.regex_lookup == {}


def test_watch_remove_keeps_item_when_event_has_functions() -> None:
    """Without force, a watch whose event has functions is kept."""
    event = MagicMock()
    event.isempty.return_value = False
    stub = _plugin({"plugins.core.events:event.get": lambda _name: event})
    stub.watch_data["w"] = _item("w", regex=r"^go")
    stub.regex_lookup[r"^go"] = "w"

    assert WatchPlugin._api_watch_remove(stub, "w", force=False) is False
    assert "w" in stub.watch_data
    assert r"^go" in stub.regex_lookup


def _command_stub(args: dict[str, Any], detail: Any = None) -> Any:
    """Return a stub plugin for the list and detail commands."""
    api_map: dict[str, Any] = {
        "plugins.core.commands:command.current.args.get": lambda: args,
    }
    if detail is not None:
        api_map["plugins.core.events:event.detail.get"] = detail
    stub = _plugin(api_map)
    stub.watch_data = {
        "alpha": _item("alpha", owner="plugins.x", hits=3),
        "beta": _item("beta", regex="^b", owner="plugins.y"),
    }
    return stub


def test_command_list_lists_and_filters() -> None:
    """The list command shows every watch and filters by name or owner."""
    result = WatchPlugin._command_list(_command_stub({"match": ""}))
    all_lines = result.message
    text = "\n".join(all_lines)
    assert "alpha" in text
    assert "beta" in text

    result = WatchPlugin._command_list(_command_stub({"match": "alp"}))
    by_name = result.message
    assert "alpha" in "\n".join(by_name)
    assert "beta" not in "\n".join(by_name)

    result = WatchPlugin._command_list(_command_stub({"match": "plugins.y"}))
    by_owner = result.message
    assert "beta" in "\n".join(by_owner)
    assert "alpha" not in "\n".join(by_owner)


def test_command_detail_existing_watch() -> None:
    """Bug 1: detail of an existing watch must not raise KeyError."""
    detail = MagicMock(return_value=["event detail line"])
    stub = _command_stub({"watch": ["alpha"]}, detail)
    result = WatchPlugin._command_detail(stub)
    message = result.message

    detail.assert_called_once_with("watch_alpha")
    text = "\n".join(message)
    assert "alpha" in text
    assert "plugins.x" in text
    assert "^say" in text
    assert "3" in text
    assert "event detail line" in message


def test_command_detail_unknown_watch() -> None:
    """An unknown watch name is reported, not raised."""
    result = WatchPlugin._command_detail(_command_stub({"watch": ["nope"]}))
    message = result.message
    assert message == ["watch nope does not exist"]
