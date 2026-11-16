"""Pages draw their rules and headers at the client's line length (#421)."""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from bastproxy.plugins.core.commands.plugin._commands import CommandsPlugin
from bastproxy.plugins.core.events.plugin._events import EventsPlugin
from bastproxy.plugins.core.log.plugin._log import LogPlugin
from bastproxy.plugins.core.timers.plugin._timers import TimersPlugin

PID = "plugins.core.commands"
WIDTH = 50


def _stub(
    plugin_id: str = PID,
    extra: dict[str, Callable[..., Any]] | None = None,
) -> tuple[MagicMock, list[tuple[str, tuple[Any, ...], dict[str, Any]]], list[str]]:
    """Return a stub, the recorded cap/center calls and the recorded width reads."""
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    width_reads: list[str] = []

    def width() -> int:
        width_reads.append("read")
        return WIDTH

    def record(name: str) -> Callable[..., str]:
        def _call(*a: Any, **k: Any) -> str:
            calls.append((name, a, k))
            return name

        return _call

    table: dict[str, Callable[..., Any]] = {
        "plugins.core.settings:setting.get": lambda _pid, _key: "@w",
        f"{PID}:output.header.format": lambda title: [f"HEADER {title}"],
        "plugins.core.proxy:line.length.get": width,
        "plugins.core.utils:line.cap": record("cap"),
        "plugins.core.utils:string.center.colored": record("center"),
        "libs.plugins.loader:plugin.list.in.package": lambda _pkg: [],
        "libs.plugins.loader:package.list": lambda active_only: [],
        "plugins.core.utils:column.format": lambda *_a, **_k: [],
        f"{PID}:command.list.formatted": lambda _pid: [],
        f"{PID}:command.data.get": lambda _pid: {},
        "plugins.core.commands:command.current.args.get": lambda: {"match": ""},
    }
    table.update(extra or {})
    stub = MagicMock()
    stub.plugin_id = plugin_id
    stub.api = lambda name: table[name]
    stub.proxy_help = lambda *a: CommandsPlugin.proxy_help(stub, *a)
    return stub, calls, width_reads


def _assert_error_widths(calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]]) -> None:
    cap = next(c for c in calls if c[0] == "cap")
    center = next(c for c in calls if c[0] == "center")
    assert cap[1][0] == "-" * (WIDTH - 2)
    assert cap[2]["line_length"] == WIDTH
    assert center[2]["length"] == WIDTH


def test_error_package_not_found_uses_client_width() -> None:
    stub, calls, _ = _stub()
    CommandsPlugin.error_package_not_found(stub, "zzz")
    _assert_error_widths(calls)


def test_error_plugin_not_found_uses_client_width() -> None:
    stub, calls, _ = _stub()
    CommandsPlugin.error_plugin_not_found(stub, "zzz", "plugins.core")
    _assert_error_widths(calls)


def test_error_command_not_found_uses_client_width() -> None:
    stub, calls, _ = _stub()
    CommandsPlugin.error_command_not_found_in_plugin(stub, PID, "zzz")
    _assert_error_widths(calls)


def test_proxy_help_rule_uses_client_width() -> None:
    stub, _, _ = _stub()
    out = CommandsPlugin.proxy_help(stub, "T", "Second", [])
    assert "@B" + "-" * WIDTH in out


def test_proxy_help_without_header2_reads_no_width() -> None:
    stub, _, reads = _stub()
    CommandsPlugin.proxy_help(stub, "T", "", [])
    assert reads == []


def _no_width_arg(calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]]) -> None:
    centers = [c for c in calls if c[0] == "center"]
    assert len(centers) == 2
    for _, args, kwargs in centers:
        assert 80 not in args
        assert "length" not in kwargs
        assert len(args) == 2


def test_commands_summary_leaves_width_to_the_default() -> None:
    stub, calls, _ = _stub()
    CommandsPlugin._api_summary_get_for_plugin(stub, PID)
    _no_width_arg(calls)


def test_events_summary_leaves_width_to_the_default() -> None:
    eid = "plugins.core.events"
    stub, calls, _ = _stub(eid, {f"{eid}:x": lambda: None})
    stub.events = {}
    stub.global_raised_count = 0
    EventsPlugin._api_summary_get_for_plugin(stub, eid)
    _no_width_arg(calls)


def test_timers_list_rules_use_client_width() -> None:
    stub, _, _ = _stub("plugins.core.timers")
    stub.timer_lookup = {}
    result = TimersPlugin._command_list(stub)
    rules = [m for m in result.message if set(m.strip("@wGBCRY")) == {"-"}]
    assert len(rules) == 2
    assert all(r == "@w" + "-" * WIDTH + "@w" for r in rules)


def test_log_types_rules_use_client_width() -> None:
    stub, _, _ = _stub("plugins.core.log")
    stub.handlers = {"client": {"a.b": "info"}, "console": {}, "file": {}}
    stub.type_counts = {}
    stub.logtype_col_length = 35
    result = LogPlugin._command_types(stub)
    rules = [m for m in result.message if m and set(m) == {"-"}]
    assert rules == ["-" * WIDTH] * 2
