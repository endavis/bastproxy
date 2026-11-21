# Project: bastproxy
# Filename: tests/plugins/client/aliases/test_aliases.py
#
# File Description: Tests for the aliases plugin
#
# By: Bast
"""Unit tests for `plugins.client.aliases` (issue #708)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.plugins import imputils
from bastproxy.libs.records import UpdateFlag
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.client.aliases.plugin import _aliases as aliases_module
from bastproxy.plugins.client.aliases.plugin._aliases import (
    ALIAS_PRIORITY,
    MAX_DEPTH,
    AliasesPlugin,
    substitute_arguments,
)
from bastproxy.plugins.client.variables.plugin._variables import EXPAND_PRIORITY

SPLIT = r"(?<=[^\|])\|(?=[^\|])"


class FakeApi:
    """A stand-in for the plugin api: callable, with the split regex attribute."""

    command_split_regex: str | None = SPLIT
    command_separator: str = "|"

    def __init__(self, table: dict[str, Callable[..., Any]]) -> None:
        self.table = table

    def __call__(self, name: str) -> Callable[..., Any]:
        return self.table[name]


def _plugin(tmp_path: Path, args: dict[str, Any] | None = None) -> Any:
    plugin: Any = object.__new__(AliasesPlugin)
    plugin.plugin_id = "plugins.client.aliases"
    plugin.aliases = PersistentDict("x", tmp_path / "aliases.txt", "c")
    plugin.groups = PersistentDict("x", tmp_path / "groups.txt", "c")
    plugin.session_hits = {}
    plugin._resend_depth = 0
    plugin.escape = MagicMock(side_effect=lambda s: s.replace("@", "@@"))
    plugin.run = MagicMock()
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.commands:command.prefix.get": lambda: "#bp",
        "plugins.core.commands:command.current.args.get": lambda: args,
        "plugins.core.colors:colorcode.escape": plugin.escape,
        "plugins.core.commands:command.line.run": plugin.run,
        "plugins.client.aliases:alias.add": plugin._api_alias_add,
        "plugins.client.aliases:alias.remove": plugin._api_alias_remove,
        "plugins.client.aliases:alias.enabled.set": plugin._api_alias_enabled_set,
        "plugins.client.aliases:alias.group.enabled.set": plugin._api_alias_group_enabled_set,
    }
    plugin.api = FakeApi(table)
    return plugin


@pytest.mark.parametrize(
    ("expansion", "rest", "expected"),
    [
        ("%1 %2", "a b", "a b"),
        ("x %3 y", "a b", "x  y"),
        ("say %*", "  hello  there ", "say hello  there"),
        ("say %%1", "", "say %1"),
        ("say %%* %%1", "x", "say %* %1 x"),
        ("kill %{t}", "", "kill %{t}"),
        ("kill %%{t}", "", "kill %%{t}"),
        ("open all", "door", "open all door"),
        ("open all", "", "open all"),
        ("echo %1", "%2 b", "echo %2"),
        ("a %10", "x", "a x0"),
        ("%1 %1", "q", "q q"),
    ],
)
def test_substitute_arguments(expansion: str, rest: str, expected: str) -> None:
    """Arguments substitute in one pass, with the escape and append rule."""
    assert substitute_arguments(expansion, rest) == expected


def test_add_get_exists_list_remove(tmp_path: Path) -> None:
    """The API stores, reads and removes aliases; get and list return copies."""
    p = _plugin(tmp_path)
    assert p._api_alias_add("k", "kill %1") is True
    assert p._api_alias_get("k") == {"expansion": "kill %1", "group": "", "enabled": True}
    assert p._api_alias_get("zz") is None
    assert p._api_alias_exists("k") is True
    got = p._api_alias_get("k")
    got["expansion"] = "changed"
    listed = p._api_alias_list()
    listed["k"]["expansion"] = "changed"
    listed["new"] = {}
    assert p.aliases["k"]["expansion"] == "kill %1"
    assert p._api_alias_exists("new") is False
    p.session_hits["k"] = 2
    assert p._api_alias_remove("k") is True
    assert p._api_alias_remove("k") is False
    assert "k" not in p.session_hits


@pytest.mark.parametrize(
    ("name", "expansion", "group"),
    [
        ("a b", "x", ""),
        ("a\tb", "x", ""),
        ("", "x", ""),
        ("a%", "x", ""),
        ("#bpx", "x", ""),
        ("a|b", "x", ""),
        ("a", "", ""),
        ("a", "   ", ""),
        ("a", "x\ny", ""),
        ("a", "x\ry", ""),
        ("a", "x", "bad group"),
        ("a", "x", "g-1"),
        (5, "x", ""),
        ("a", 5, ""),
    ],
)
def test_add_refuses_bad_input(tmp_path: Path, name: Any, expansion: Any, group: str) -> None:
    """A bad name, expansion or group is refused and nothing is stored."""
    p = _plugin(tmp_path)
    assert p._api_alias_add(name, expansion, group) is False
    assert dict(p.aliases) == {}


def test_enabled_state(tmp_path: Path) -> None:
    """An alias is enabled only when it and its group are enabled."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "x", "g")
    p._api_alias_add("b", "y", "g")
    p._api_alias_add("c", "z")
    assert p._api_alias_is_enabled("a") is True
    assert p._api_alias_is_enabled("missing") is False
    assert p._api_alias_enabled_set("a", False) is True
    assert p._api_alias_enabled_set("missing", False) is False
    assert p._api_alias_is_enabled("a") is False
    assert p._api_alias_group_enabled_set("g", False) == 2
    assert p._api_alias_group_is_enabled("g") is False
    assert p._api_alias_is_enabled("b") is False
    assert p._api_alias_is_enabled("c") is True
    p._api_alias_enabled_set("a", True)
    assert p._api_alias_is_enabled("a") is False
    p._api_alias_group_enabled_set("g", True)
    assert p._api_alias_is_enabled("a") is True
    assert p._api_alias_group_is_enabled("never") is True


def test_persistence(tmp_path: Path) -> None:
    """Aliases and group state survive new PersistentDicts on the same files."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "x", "g")
    p._api_alias_group_enabled_set("g", False)
    assert dict(PersistentDict("x", tmp_path / "aliases.txt", "c")) == {
        "a": {"expansion": "x", "group": "g", "enabled": True}
    }
    assert dict(PersistentDict("x", tmp_path / "groups.txt", "c")) == {"g": False}
    p._api_alias_remove("a")
    assert dict(PersistentDict("x", tmp_path / "aliases.txt", "c")) == {}


def test_command_add(tmp_path: Path) -> None:
    """add joins the expansion and takes a group and the disabled flag."""
    args = {"name": "k", "expansion": ["kill", "%1"], "group": "g", "disabled": True}
    p = _plugin(tmp_path, args)
    assert p._command_add().success is True
    assert p.aliases["k"] == {"expansion": "kill %1", "group": "g", "enabled": False}


def test_command_add_stores_doubled_separator_single(tmp_path: Path) -> None:
    """A typed ``||`` (the way to type one separator in a command) is stored as ``|``."""
    args = {"name": "p", "expansion": ["stand||look||say", "%*"], "group": "", "disabled": False}
    p = _plugin(tmp_path, args)
    assert p._command_add().success is True
    assert p.aliases["p"]["expansion"] == "stand|look|say %*"


def test_api_add_keeps_expansion_literal(tmp_path: Path) -> None:
    """The API stores what the caller passes; only the typed command unescapes."""
    p = _plugin(tmp_path)
    assert p._api_alias_add("p", "a||b") is True
    assert p.aliases["p"]["expansion"] == "a||b"


def test_command_add_failures(tmp_path: Path) -> None:
    """No expansion and a bad name are errors."""
    empty = _plugin(tmp_path, {"name": "k", "expansion": [], "group": "", "disabled": False})
    assert empty._command_add().success is False
    bad_args = {"name": "a%", "expansion": ["x"], "group": "", "disabled": False}
    bad = _plugin(tmp_path, bad_args)
    assert bad._command_add().success is False


def test_command_remove(tmp_path: Path) -> None:
    """remove of an unknown alias fails, of a known one succeeds."""
    p = _plugin(tmp_path, {"name": "k"})
    result = p._command_remove()
    assert result.success is False
    assert "does not exist" in str(result.message)
    p._api_alias_add("k", "x")
    assert p._command_remove().success is True


def test_command_list(tmp_path: Path) -> None:
    """list filters, escapes and reports an empty store and disabled aliases."""
    p = _plugin(tmp_path, {"match": ""})
    assert "No aliases defined" in str(p._command_list().message)
    p._api_alias_add("red", "@r", "g")
    p._api_alias_add("blue", "b")
    p._api_alias_enabled_set("blue", False)
    assert p._command_list().message == ["blue : b (disabled)", "red : @@r (group g)"]
    p.api.table["plugins.core.commands:command.current.args.get"] = lambda: {"match": "re"}
    assert p._command_list().message == ["red : @@r (group g)"]


def test_command_enable_disable(tmp_path: Path) -> None:
    """enable and disable work by name or by group, with exactly one given."""
    p = _plugin(tmp_path, {"name": "a", "group": ""})
    p._api_alias_add("a", "x", "g")
    assert p._command_disable().success is True
    assert p._api_alias_is_enabled("a") is False
    assert p._command_enable().success is True
    assert p._api_alias_is_enabled("a") is True
    set_args = p.api.table
    set_args["plugins.core.commands:command.current.args.get"] = lambda: {"name": "", "group": "g"}
    result = p._command_disable()
    assert result.success is True
    assert "1 aliases" in str(result.message)
    assert p._api_alias_group_is_enabled("g") is False
    assert p._command_enable().success is True
    set_args["plugins.core.commands:command.current.args.get"] = lambda: {"name": "", "group": ""}
    assert p._command_enable().success is False
    set_args["plugins.core.commands:command.current.args.get"] = lambda: {"name": "a", "group": "g"}
    assert p._command_disable().success is False
    set_args["plugins.core.commands:command.current.args.get"] = lambda: {"name": "zz", "group": ""}
    assert p._command_enable().success is False


def test_command_show(tmp_path: Path) -> None:
    """show reports the alias, and fails for an unknown one."""
    p = _plugin(tmp_path, {"name": "a"})
    assert p._command_show().success is False
    p._api_alias_add("a", "x @r", "g")
    p.session_hits["a"] = 3
    message = p._command_show().message
    assert "expansion     : x @@r" in message
    assert "session hits  : 3" in message


def _run(
    p: Any, text: str, *, record: Any = "default", client_id: str | None = "c1"
) -> tuple[NetworkDataLine, MagicMock]:
    line = NetworkDataLine(text, originated="client")
    event_record = MagicMock()
    values = {"line": line, "client_id": client_id}
    event_record.__getitem__.side_effect = lambda key: values[key]
    rec = event_record if record == "default" else record
    p.api.table["plugins.core.events:event.current.record.get"] = lambda: rec
    p._eventcb_expand_line()
    return line, event_record


def test_callback_rewrites_in_place(tmp_path: Path) -> None:
    """A single-line expansion rewrites the line, records it and counts the hit."""
    p = _plugin(tmp_path)
    p._api_alias_add("k", "kill %1")
    line, record = _run(p, "  k orc")
    assert line.line == "kill orc"
    assert line.send is True
    assert line.line_modified is True
    record.addupdate.assert_called_once()
    assert record.addupdate.call_args.args[0] == UpdateFlag.MODIFY
    assert p.session_hits == {"k": 1}
    p.run.assert_not_called()


def test_callback_leaves_other_lines(tmp_path: Path) -> None:
    """A disabled alias, a disabled group, a non-alias and a case change are unchanged."""
    p = _plugin(tmp_path)
    p._api_alias_add("off", "x", enabled=False)
    p._api_alias_add("grp", "x", "g")
    p._api_alias_group_enabled_set("g", False)
    p._api_alias_add("k", "kill")
    for text in ["off a", "grp a", "look", "K orc", ""]:
        line, record = _run(p, text)
        assert line.line == text
        record.addupdate.assert_not_called()


@pytest.mark.parametrize("text", ["#bp.client.aliases.list k", "  #bp x k"])
def test_callback_skips_command_lines(tmp_path: Path, text: str) -> None:
    """Command-prefix lines are not expanded."""
    p = _plugin(tmp_path)
    p._api_alias_add("k", "kill")
    line, _ = _run(p, text)
    assert line.line == text


def test_callback_skips_masked_unsent_non_io_and_no_record(tmp_path: Path) -> None:
    """Masked, unsent and non-I/O lines are not expanded; a missing record returns."""
    p = _plugin(tmp_path)
    p._api_alias_add("k", "kill")
    line = NetworkDataLine("k", originated="client")
    for change in ("mask", "unsent"):
        line = NetworkDataLine("k", originated="client")
        if change == "mask":
            line.mask_log = True
        else:
            line.send = False
        record = MagicMock()
        record.__getitem__.side_effect = lambda key, line=line: line
        p.api.table["plugins.core.events:event.current.record.get"] = lambda record=record: record
        p._eventcb_expand_line()
        assert line.line == "k"
    non_io = NetworkDataLine("k", originated="client", line_type="COMMAND-TELNET")
    record = MagicMock()
    record.__getitem__.side_effect = lambda key: non_io
    p.api.table["plugins.core.events:event.current.record.get"] = lambda: record
    p._eventcb_expand_line()
    assert non_io.line == "k"
    line, _ = _run(p, "k", record=None)
    assert line.line == "k"


def test_callback_chain_resolves_in_place(tmp_path: Path) -> None:
    """An expansion starting with another alias resolves in place."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "b one")
    p._api_alias_add("b", "kill %1")
    line, record = _run(p, "a two")
    assert line.line == "kill one"
    assert record.addupdate.call_count == 1
    p.run.assert_not_called()


@pytest.mark.parametrize("expansion", ["look|kill %1", "#bp.client.aliases.list"])
def test_callback_resends_separator_and_commands(tmp_path: Path, expansion: str) -> None:
    """A separator or command-prefix expansion is re-sent and the typed line dropped."""
    p = _plugin(tmp_path)
    p._api_alias_add("go", expansion)
    line, _ = _run(p, "go orc")
    assert line.send is False
    expected = expansion.replace("%1", "orc") if "%1" in expansion else expansion + " orc"
    p.run.assert_called_once_with(expected, show_in_history=False)
    assert p._resend_depth == 0


def test_self_reference_stops_at_max_depth(tmp_path: Path) -> None:
    """An alias that expands to itself is not sent, the client is told and it is logged."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "a")
    with (
        patch.object(aliases_module, "SendDataDirectlyToClient") as send,
        patch.object(aliases_module, "log_to") as log,
    ):
        line, _ = _run(p, "a")
    assert line.send is False
    assert p.session_hits == {"a": MAX_DEPTH}
    send.assert_called_once()
    assert send.call_args.kwargs == {"clients": ["c1"]}
    log.assert_called_once()


def test_resend_recursion_is_bounded(tmp_path: Path) -> None:
    """An alias that expands to `x|a` enters command.line.run at most MAX_DEPTH times."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "x|a")
    depths: list[int] = []

    def run(text: str, show_in_history: bool = False) -> None:
        depths.append(p._resend_depth)
        # the input path splits on the separator and runs each part
        for part in text.split("|"):
            _run(p, part)

    p.run.side_effect = run
    with (
        patch.object(aliases_module, "SendDataDirectlyToClient"),
        patch.object(aliases_module, "log_to"),
    ):
        _run(p, "a")
    assert p.run.call_count == MAX_DEPTH
    assert depths == list(range(1, MAX_DEPTH + 1))
    assert p._resend_depth == 0


def test_resend_depth_restored_when_run_raises(tmp_path: Path) -> None:
    """The depth counter is back to 0 after command.line.run raises."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "x|y")
    p.run.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        _run(p, "a")
    assert p._resend_depth == 0


def test_stop_without_client_sends_nothing(tmp_path: Path) -> None:
    """With no client on the record the limit message is skipped."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "a")
    with (
        patch.object(aliases_module, "SendDataDirectlyToClient") as send,
        patch.object(aliases_module, "log_to"),
    ):
        line, _ = _run(p, "a", client_id=None)
    assert line.send is False
    send.assert_not_called()


def test_callback_priority_between_commands_and_variables() -> None:
    """The callback registers at 55: after commands (50), before variables (60)."""
    args = AliasesPlugin._eventcb_expand_line.event_registration
    assert args == [{"event_name": "ev_to_mud_data_modify", "priority": ALIAS_PRIORITY}]
    assert 50 < ALIAS_PRIORITY < EXPAND_PRIORITY


def test_plugin_is_discovered() -> None:
    """Discovery finds the plugin under the plugins.client package."""
    plugins_dir = Path(__file__).resolve().parents[4] / "src" / "bastproxy" / "plugins"
    result = imputils.find_packages_and_plugins(plugins_dir, "bastproxy.plugins.")
    ids = [item["plugin_id"] for item in result.plugins]
    assert "bastproxy.plugins.client.aliases" in ids
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
    own_names = _command_names(dict(vars(AliasesPlugin)))

    assert {"set", "reset", "save", "help"} <= base_names
    assert own_names == {"add", "remove", "list", "enable", "disable", "show"}
    assert not own_names & base_names
