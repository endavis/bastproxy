"""The shorter fixed-width rules clamp to the client's line length (#508)."""

import datetime
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.api import API
from bastproxy.plugins._baseplugin.libs._commands import Commands
from bastproxy.plugins.core.events.libs.process._raisedevent import ProcessRaisedEvent
from bastproxy.plugins.core.events.plugin._event import Event
from bastproxy.plugins.core.sqldb.libs._sqlite import Sqldb
from bastproxy.plugins.core.triggers.plugin._triggers import TriggersPlugin
from bastproxy.plugins.core.watch.plugin._watch import WatchPlugin

LL = "plugins.core.proxy:line.length.get"
CENTER = "plugins.core.utils:string.center.colored"


def _api(
    width: int, extra: dict[str, Callable[..., Any]] | None = None
) -> tuple[Callable[[str], Any], list[tuple[tuple[Any, ...], dict[str, Any]]]]:
    """Return an api dispatcher and the recorded center calls."""
    centers: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def center(*a: Any, **k: Any) -> str:
        centers.append((a, k))
        return "CENTER"

    table: dict[str, Callable[..., Any]] = {
        LL: lambda: width,
        CENTER: center,
        "plugins.core.settings:setting.get": lambda _pid, _key: "@w",
        "plugins.core.commands:command.current.args.get": lambda: {"match": ""},
    }
    table.update(extra or {})
    return (lambda name: table[name]), centers


def _rules(lines: list[str]) -> list[int]:
    """Return the length of every line that is only a dash rule."""
    return [len(s) for m in lines if (s := m.strip("@wGBCRY")) and set(s) == {"-"}]


def _lengths(centers: list[tuple[tuple[Any, ...], dict[str, Any]]]) -> list[int]:
    return [a[2] for a, _ in centers]


@pytest.mark.parametrize(("width", "expected"), [(45, 45), (100, 60)])
def test_plugin_help(width: int, expected: int) -> None:
    api, centers = _api(
        width,
        {
            "libs.plugins.loader:plugin.file.list.changed": lambda _pid: ["a.py"],
            "libs.plugins.loader:plugin.file.list.invalid": lambda _pid: ["b.py"],
            "plugins.core.commands:command.list.formatted": lambda _pid: [],
            "libs.api:api.list.formatted": lambda _pid: ["x"],
        },
    )
    stub = MagicMock()
    stub.api = MagicMock(
        side_effect=lambda name: (
            (lambda: {"commands": True, "api": True})
            if name == "plugins.core.commands:command.current.args.get"
            else api(name)
        )
    )
    stub.api.time_format = "%Y"
    stub.plugin_id = "plugins.core.x"
    stub.loaded_time = datetime.datetime.now(datetime.UTC)
    stub.plugin_info.package_import_location = "bastproxy"
    stub.plugin_info.package_path = "p"
    result = Commands._command_help(stub)
    assert _lengths(centers) == [expected, expected]
    assert _rules(result.message) == [expected] * 4


@pytest.mark.parametrize(("width", "expected"), [(45, 45), (100, 60)])
def test_event_detail(width: int, expected: int) -> None:
    api, centers = _api(width)
    stub = MagicMock()
    stub.api = api
    stub.description = ["d"]
    stub.priority_dictionary = {}
    stub.arg_descriptions = {}
    result = Event.detail(stub)
    assert _lengths(centers) == [expected, expected]
    assert _rules(result) == [expected] * 3


@pytest.mark.parametrize(
    ("width", "expected"), [(35, (35, 35, 35)), (45, (45, 40, 40)), (100, (50, 40, 40))]
)
def test_raised_event_format_simple(width: int, expected: tuple[int, int, int]) -> None:
    api, centers = _api(width)
    stub = MagicMock()
    stub.api = api
    stub.created = "now"
    stub.called_from = "here"
    stub.event_data = "data"
    stub.event_stack = []
    stub.stack_at_creation = []
    ProcessRaisedEvent.format_simple(stub)
    assert tuple(_lengths(centers)) == expected


@pytest.mark.parametrize(("width", "expected"), [(45, 45), (100, 60)])
def test_trigger_list(width: int, expected: int) -> None:
    api, _ = _api(width)
    stub = MagicMock()
    stub.api = api
    stub.triggers = {}
    assert _rules(TriggersPlugin._command_list(stub).message) == [expected]


@pytest.mark.parametrize(("width", "expected"), [(45, 45), (100, 60)])
def test_watch_list(width: int, expected: int) -> None:
    api, _ = _api(width)
    stub = MagicMock()
    stub.api = api
    stub.watch_data = {}
    assert _rules(WatchPlugin._command_list(stub).message) == [expected]


@pytest.mark.parametrize(("width", "expected"), [(35, 35), (45, 40), (100, 40)])
def test_dbtables_rule(width: int, expected: int) -> None:
    api, _ = _api(width, {"plugins.core.commands:command.current.args.get": lambda: {"table": "t"}})
    stub = MagicMock()
    stub.api = api
    stub.checktable.return_value = True
    stub.db_connection.cursor.return_value.fetchall.return_value = []
    result = Sqldb._command_dbtables(stub)
    assert _rules(result.message) == [expected]


@pytest.fixture
def _isolated_api() -> Iterator[None]:
    class_api = dict(API._class_api)
    yield
    API._class_api.clear()
    API._class_api.update(class_api)


@pytest.mark.usefixtures("_isolated_api")
@pytest.mark.parametrize(("width", "expected"), [(45, 45), (100, 50)])
def test_api_list_formatted_clamps(width: int, expected: int) -> None:
    api = API(owner_id="short_rule_owner")
    api.add("shortrule", "n", lambda: 1, description="d")
    api.add("plugins.core.proxy", "line.length.get", lambda: width, instance=True)
    api.add("libs.plugins.loader", "plugin.id.is.valid", lambda _pid: False, instance=True)
    lines = api("libs.api:api.list.formatted")("shortrule")
    assert _rules(lines) == [expected]


@pytest.mark.usefixtures("_isolated_api")
def test_api_list_formatted_without_proxy_plugin() -> None:
    API._class_api.pop(LL, None)
    api = API(owner_id="short_rule_owner")
    api.add("shortrule", "n", lambda: 1, description="d")
    assert _rules(api("libs.api:api.list.formatted")("shortrule")) == [50]
