# Project: bastproxy
# Filename: tests/plugins/client/loop/test_loop.py
#
# File Description: Tests for the loop plugin
#
# By: Bast
"""Unit tests for `plugins.client.loop` (issue #711)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.libs import argp
from bastproxy.libs.plugins import imputils
from bastproxy.plugins.client.loop.plugin import _loop as loop_module
from bastproxy.plugins.client.loop.plugin._loop import (
    MAX_COUNT,
    MAX_TOTAL,
    LoopPlugin,
    substitute_counter,
)


class FakeApi:
    """A stand-in for the plugin api: callable, with the separator attribute."""

    command_separator: str = "|"

    def __init__(self, table: dict[str, Callable[..., Any]]) -> None:
        self.table = table

    def __call__(self, name: str) -> Callable[..., Any]:
        return self.table[name]


def _plugin(args: dict[str, Any] | None = None) -> Any:
    plugin: Any = object.__new__(LoopPlugin)
    plugin.plugin_id = "plugins.client.loop"
    plugin._depth = 0
    plugin._total = 0
    plugin._stopped = False
    plugin.escape = MagicMock(side_effect=lambda s: s.replace("@", "@@"))
    plugin.run = MagicMock()
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.commands:command.current.args.get": lambda: args,
        "plugins.core.colors:colorcode.escape": plugin.escape,
        "plugins.core.commands:command.line.run": plugin.run,
    }
    plugin.api = FakeApi(table)
    return plugin


def _lines(plugin: Any) -> list[str]:
    return [call.args[0] for call in plugin.run.call_args_list]


@pytest.mark.parametrize(
    ("template", "counter", "expected"),
    [
        ("get %1.corpse", 3, "get 3.corpse"),
        ("get %%1.corpse", 3, "get %1.corpse"),
        ("%10", 3, "30"),
        ("%1 %1", 3, "3 3"),
        ("north", 3, "north"),
        ("kill %{t}", 3, "kill %{t}"),
        ("kill %%{t}", 3, "kill %%{t}"),
        ("%2 %*", 3, "%2 %*"),
    ],
)
def test_substitute_counter(template: str, counter: int, expected: str) -> None:
    """The counter replaces %1 in one pass and nothing else changes."""
    assert substitute_counter(template, counter) == expected


def test_command_runs_each_pass_in_order() -> None:
    """The command sends each pass through command.line.run, not in the history."""
    p = _plugin({"count": "3", "template": ["get", "%1.corpse"]})
    result = p._command_run()
    assert _lines(p) == ["get 1.corpse", "get 2.corpse", "get 3.corpse"]
    assert all(call.kwargs == {"show_in_history": False} for call in p.run.call_args_list)
    assert result.success is True
    assert "3" in result.message[0]


@pytest.mark.parametrize("count", ["0", "-3", "51", "abc", "3.5", ""])
def test_bad_count_is_refused(count: str) -> None:
    """A bad count is refused and nothing runs."""
    p = _plugin({"count": count, "template": ["x"]})
    result = p._command_run()
    assert result.success is False
    assert "1 to 50" in result.message[0]
    p.run.assert_not_called()


def test_max_count_is_accepted() -> None:
    """The largest count is allowed."""
    p = _plugin({"count": str(MAX_COUNT), "template": ["x"]})
    assert p._command_run().success is True
    assert p.run.call_count == MAX_COUNT


def test_empty_template_is_refused() -> None:
    """A command with no line is refused."""
    p = _plugin({"count": "2", "template": []})
    result = p._command_run()
    assert result.success is False
    assert "line" in result.message[0]
    p.run.assert_not_called()


def test_separator_is_split_per_pass() -> None:
    """A typed stand||look %1 reaches command.line.run as stand|look 1."""
    p = _plugin({"count": "1", "template": ["stand||look", "%1"]})
    p._command_run()
    assert _lines(p) == ["stand|look 1"]


def test_api_sends_template_unchanged() -> None:
    """loop.run does not collapse a doubled separator."""
    p = _plugin()
    assert p._api_loop_run("a||b", 1) is True
    assert _lines(p) == ["a||b"]


def test_api_bad_count_logs_and_returns_false() -> None:
    """A bad count returns False, logs a warning and runs nothing."""
    p = _plugin()
    with patch.object(loop_module, "log_to") as log:
        assert p._api_loop_run("x", 0) is False
    log.assert_called_once()
    assert log.call_args.args[1] == 30
    p.run.assert_not_called()


def _nested_run(p: Any, inner: int) -> None:
    """Make command.line.run call the loop again for lines that start with a loop."""

    def run(line: str, **_kw: Any) -> None:
        p.sent.append(line)
        if line.startswith("loop "):
            p._api_loop_run(line.removeprefix("loop "), inner)

    p.sent = []
    p.run.side_effect = run


def test_nesting_within_the_cap() -> None:
    """Outer 3 over inner 2 runs six inner lines, with the escaped counter."""
    p = _plugin()
    _nested_run(p, 2)
    assert p._api_loop_run("loop get %%1.item %1.bag", 3) is True
    inner = [line for line in p.sent if not line.startswith("loop ")]
    assert inner == [
        "get 1.item 1.bag",
        "get 2.item 1.bag",
        "get 1.item 2.bag",
        "get 2.item 2.bag",
        "get 1.item 3.bag",
        "get 2.item 3.bag",
    ]
    assert (p._depth, p._total, p._stopped) == (0, 0, False)


def test_nesting_past_the_cap_is_stopped() -> None:
    """Outer 50 over inner 10 stops at the limit and resets its counters."""
    p = _plugin()
    _nested_run(p, 10)
    with patch.object(loop_module, "log_to") as log:
        assert p._api_loop_run("loop x", 50) is False
    assert len(p.sent) <= MAX_TOTAL
    assert "limit of 200" in str(log.call_args_list[-1])
    assert (p._depth, p._total, p._stopped) == (0, 0, False)


def test_command_reports_a_stopped_loop() -> None:
    """The command result says how many passes ran when nesting hit the limit."""
    p = _plugin({"count": "50", "template": ["loop", "x"]})
    _nested_run(p, 10)
    result = p._command_run()
    assert result.success is False
    assert result.message[0].startswith("ran ")
    assert "of 50" in result.message[0]
    assert "limit of 200" in result.message[0]


def test_self_calling_loop_ends_within_the_cap() -> None:
    """A loop whose line starts the same loop again ends within MAX_TOTAL."""
    p = _plugin()
    p.sent = []

    def run(line: str, **_kw: Any) -> None:
        p.sent.append(line)
        if line == "again":
            p._api_loop_run("again", 50)

    p.run.side_effect = run
    with patch.object(loop_module, "log_to"):
        p._api_loop_run("again", 50)
    assert len(p.sent) <= MAX_TOTAL
    assert (p._depth, p._total, p._stopped) == (0, 0, False)


def test_counters_restored_when_run_raises() -> None:
    """The counters are back to zero after command.line.run raises."""
    p = _plugin()
    p.run.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        p._api_loop_run("x", 3)
    assert (p._depth, p._total, p._stopped) == (0, 0, False)


def test_message_escapes_the_template() -> None:
    """The success message escapes color codes in the template."""
    p = _plugin({"count": "1", "template": ["say", "@Rhi"]})
    result = p._command_run()
    assert result.message == ['"say @@Rhi" ran 1 times']
    p.escape.assert_called_once_with("say @Rhi")


def test_plugin_is_discovered() -> None:
    """Discovery finds the plugin under the plugins.client package."""
    plugins_dir = Path(__file__).resolve().parents[4] / "src" / "bastproxy" / "plugins"
    result = imputils.find_packages_and_plugins(plugins_dir, "bastproxy.plugins.")
    ids = [item["plugin_id"] for item in result.plugins]
    assert "bastproxy.plugins.client.loop" in ids
    assert not result.errors


def _command_names(methods: dict[str, Any]) -> set[str]:
    """Return the command names of the decorated methods in a class namespace."""
    names: set[str] = set()
    for func in methods.values():
        data = getattr(func, "command_data", None)
        if data is None:
            continue
        name = data.command.get("name") or func.__name__.replace("_command_", " ")
        names.add(name.strip())
    return names


def test_command_names_do_not_shadow_base_plugin_commands() -> None:
    """A command named like a BasePlugin command (such as ``set``) is never reached."""
    from bastproxy.plugins._baseplugin import BasePlugin

    base_names: set[str] = set()
    for klass in BasePlugin.__mro__:
        base_names |= _command_names(dict(vars(klass)))
    own_names = _command_names(dict(vars(LoopPlugin)))

    assert {"set", "reset", "save", "help"} <= base_names
    assert own_names == {"run"}
    assert not own_names & base_names


def test_negative_count_is_a_positional() -> None:
    """The parser takes -3 as the count, so the refusal message is ours."""
    data = LoopPlugin._command_run.command_data
    parser = argp.ArgumentParser(**data.argparse["kwargs"])
    for arg in data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    parser.format_help()
    ns = parser.parse_args(["-3", "x"])
    assert ns.count == "-3"
