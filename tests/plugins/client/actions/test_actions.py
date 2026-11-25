# Project: bastproxy
# Filename: tests/plugins/client/actions/test_actions.py
#
# File Description: Tests for the actions plugin
#
# By: Bast
"""Unit tests for `plugins.client.actions` (issue #709)."""

import logging
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.plugins import imputils
from bastproxy.plugins.client.actions.plugin import _actions as actions_module
from bastproxy.plugins.client.actions.plugin._actions import ActionsPlugin, expand_command

SPLIT = r"(?<=[^\|])\|(?=[^\|])"
PID = "plugins.client.actions"


class FakeApi:
    """A stand-in for the plugin api: callable, with the split attributes."""

    command_split_regex: str | None = SPLIT
    command_separator: str = "|"

    def __init__(self, table: dict[str, Callable[..., Any]]) -> None:
        self.table = table

    def __call__(self, name: str) -> Callable[..., Any]:
        return self.table[name]


def _plugin(tmp_path: Path, args: dict[str, Any] | None = None) -> Any:
    plugin: Any = object.__new__(ActionsPlugin)
    plugin.plugin_id = PID
    plugin.actions = PersistentDict("x", tmp_path / "actions.txt", "c")
    plugin.groups = PersistentDict("x", tmp_path / "groups.txt", "c")
    plugin.state = PersistentDict("x", tmp_path / "state.txt", "c")
    plugin.session_hits = {}
    plugin.mocks = {
        key: MagicMock()
        for key in (
            "trigger.add",
            "trigger.remove",
            "trigger.get",
            "trigger.register",
            "trigger.toggle.enable",
            "trigger.remove.for.owner",
            "command.line.run",
        )
    }
    plugin.mocks["trigger.add"].return_value = SimpleNamespace(success=True, trigger=object())
    plugin.mocks["trigger.get"].return_value = None
    plugin.record = None
    table: dict[str, Callable[..., Any]] = {
        "plugins.core.commands:command.prefix.get": lambda: "#bp",
        "libs.api:api.exists": lambda location: False,
        "plugins.core.commands:command.current.args.get": lambda: args,
        "plugins.core.colors:colorcode.escape": lambda s: s.replace("@", "@@"),
        "plugins.core.events:event.current.record.get": lambda: plugin.record,
        "plugins.core.commands:command.line.run": plugin.mocks["command.line.run"],
        f"{PID}:action.add": plugin._api_action_add,
        f"{PID}:action.remove": plugin._api_action_remove,
        f"{PID}:action.enabled.set": plugin._api_action_enabled_set,
        f"{PID}:action.group.enabled.set": plugin._api_action_group_enabled_set,
    }
    for key in ("add", "remove", "get", "register", "toggle.enable", "remove.for.owner"):
        table[f"plugins.core.triggers:trigger.{key}"] = plugin.mocks[f"trigger.{key}"]
    plugin.api = FakeApi(table)
    return plugin


def _expand(command: str, groups: Any = (), named: Any = None, line: str = "") -> Any:
    return expand_command(
        command, groups, named or {}, line, split_regex=SPLIT, separator="|", prefix="#bp"
    )


@pytest.mark.parametrize(
    ("command", "groups", "named", "line", "expected"),
    [
        ("kill %1", ("orc",), {}, "", ["kill orc"]),
        ("a %1 %9", ("x",) + ("",) * 7 + ("z",), {}, "", ["a x z"]),
        ("say %*", (), {}, "the line", ["say the line"]),
        ("kill %<who>", ("orc",), {"who": "orc"}, "", ["kill orc"]),
        ("say %%1 %%* %%<who>", ("a",), {"who": "w"}, "l", ["say %1 %* %<who>"]),
        ("a %1 b", (None,), {}, "", ["a  b"]),
        ("a %10", ("x",), {}, "", ["a x0"]),
        ("a %1 %2", ("%2", "q"), {}, "", ["a %2 q"]),
        ("stand|kill %1", ("orc",), {}, "", ["stand", "kill orc"]),
        ("a %5", ("x",), {}, "", ["a "]),
    ],
)
def test_expand_references(
    command: str, groups: Any, named: Any, line: str, expected: list[str]
) -> None:
    """References substitute in one pass, with the escape and empty rules."""
    assert _expand(command, groups, named, line) == expected


def test_expand_escapes_mud_part() -> None:
    """In a MUD part the separator is doubled, %{ and @ are literal, CR/LF dropped."""
    assert _expand("say %1", ("a|b",)) == ["say a||b"]
    assert _expand("say %1", ("%{x}",)) == ["say %%{x}"]
    assert _expand("say %1", ("@r",)) == ["say @@r"]
    assert _expand("say %1", ("a\r\nb",)) == ["say ab"]


def test_expand_quotes_command_part() -> None:
    """In a proxy command part a value is one quoted argument."""
    assert _expand("#bp.x %1", ("x -g evil",)) == ["#bp.x 'x -g evil'"]
    assert _expand("#bp.x %1", ("plain",)) == ["#bp.x plain"]


def test_expand_refuses_prefix_injection() -> None:
    """A MUD part that would start with the prefix after substitution refuses the firing."""
    assert _expand("%1", ("#bp.x",)) is None
    assert _expand("  %1 y", ("#bp.x",)) is None
    assert _expand("stand|%1", ("#bp.x",)) is None
    assert _expand("#bp.x.list", ()) == ["#bp.x.list"]
    assert _expand("say %1", ("#bp.x",)) == ["say #bp.x"]


def test_expand_without_split_regex() -> None:
    """With no split regex the command is one part."""
    out = expand_command("a|b %1", ("x",), {}, "", split_regex=None, separator="|", prefix="#bp")
    assert out == ["a|b x"]


def test_add_get_exists_list_remove(tmp_path: Path) -> None:
    """The API stores, reads and removes actions; get and list return copies."""
    p = _plugin(tmp_path)
    assert p._api_action_add("k", r"^(\w+) dies", "loot %1", matchcolor=True) is True
    assert p._api_action_get("k") == {
        "regex": r"^(\w+) dies",
        "command": "loot %1",
        "group": "",
        "enabled": True,
        "matchcolor": True,
        "send": "execute",
        "id": 1,
        "hits": 0,
    }
    assert p._api_action_get("zz") is None
    assert p._api_action_exists("k") is True
    got = p._api_action_get("k")
    got["command"] = "changed"
    listed = p._api_action_list()
    listed["k"]["command"] = "changed"
    assert p.actions["k"]["command"] == "loot %1"
    p.session_hits["k"] = 2
    assert p._api_action_remove("k") is True
    assert p._api_action_remove("k") is False
    p.mocks["trigger.remove"].assert_called_with("k", force=True)
    assert "k" not in p.session_hits


@pytest.mark.parametrize(
    ("name", "regex", "command", "group"),
    [
        ("a b", "x", "y", ""),
        ("", "x", "y", ""),
        ("a-b", "x", "y", ""),
        (5, "x", "y", ""),
        ("a", "(", "y", ""),
        ("a", "", "y", ""),
        ("a", "x\ny", "y", ""),
        ("a", "x\ry", "y", ""),
        ("a", 5, "y", ""),
        ("a", "x", "", ""),
        ("a", "x", "  ", ""),
        ("a", "x", "y\nz", ""),
        ("a", "x", 5, ""),
        ("a", "(a)(b)", "say %3", ""),
        ("a", "(?P<w>a)", "say %<nope>", ""),
        ("a", "x", "y", "bad group"),
        ("a", "x", "y", "g-1"),
    ],
)
def test_add_refuses_bad_input(
    tmp_path: Path, name: Any, regex: Any, command: Any, group: str
) -> None:
    """A bad name, regex, command or group is refused and nothing is stored."""
    p = _plugin(tmp_path)
    assert p._api_action_add(name, regex, command, group) is False
    assert dict(p.actions) == {}
    p.mocks["trigger.add"].assert_not_called()


def test_add_accepts_valid_references(tmp_path: Path) -> None:
    """Numbered, named, whole-line and escaped references fit the regex."""
    p = _plugin(tmp_path)
    assert p._api_action_add("a", r"(?P<w>\w+) (\d+)", "x %1 %2 %<w> %* %%9 %%<no>") is True


def test_add_registers_trigger(tmp_path: Path) -> None:
    """A stored action gets a trigger and the callback registered."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "y", "g", enabled=False)
    p.mocks["trigger.add"].assert_called_once_with("a", "x", enabled=False, matchcolor=False)
    p.mocks["trigger.register"].assert_called_once_with("a", p._trigger_matched)


def test_add_fails_when_trigger_add_fails(tmp_path: Path) -> None:
    """A trigger that cannot be added makes the call return False."""
    p = _plugin(tmp_path)
    p.mocks["trigger.add"].return_value = SimpleNamespace(success=False, trigger=None)
    assert p._api_action_add("a", "x", "y") is False


def test_replace_removes_old_trigger_first(tmp_path: Path) -> None:
    """Replacing an action removes its trigger with force before adding."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "y")
    p.mocks["trigger.remove"].assert_not_called()
    p.mocks["trigger.get"].return_value = object()
    p._api_action_add("a", "z", "y")
    p.mocks["trigger.remove"].assert_called_once_with("a", force=True)
    assert p.actions["a"]["regex"] == "z"


def test_enabled_state_syncs_trigger(tmp_path: Path) -> None:
    """The trigger gets the effective state of the action and its group."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "y", "g")
    p._api_action_add("b", "x", "y", "g")
    p._api_action_add("c", "x", "y")
    toggle = p.mocks["trigger.toggle.enable"]
    assert p._api_action_enabled_set("a", False) is True
    assert p._api_action_enabled_set("missing", False) is False
    toggle.assert_called_with("a", False)
    assert p._api_action_is_enabled("missing") is False
    toggle.reset_mock()
    assert p._api_action_group_enabled_set("g", False) == 2
    assert {c.args for c in toggle.call_args_list} == {("a", False), ("b", False)}
    assert p._api_action_group_is_enabled("g") is False
    assert p._api_action_is_enabled("c") is True
    toggle.reset_mock()
    p._api_action_group_enabled_set("g", True)
    assert {c.args for c in toggle.call_args_list} == {("a", False), ("b", True)}
    assert p._api_action_group_is_enabled("never") is True


def test_persistence_and_after_load(tmp_path: Path) -> None:
    """Stored actions come back and after_load registers each; a broken one is logged."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "y", "g")
    assert dict(PersistentDict("x", tmp_path / "actions.txt", "c")) == {"a": p.actions["a"]}
    p.actions["bad"] = {"regex": "(", "command": "y", "group": "", "enabled": True}
    p.actions.sync()
    q = _plugin(tmp_path)
    q.mocks["trigger.add"].side_effect = lambda name, rx, **kw: SimpleNamespace(
        success=rx != "(", trigger=None
    )
    with patch.object(actions_module, "log_to") as log:
        q._phook_actions_after_load()
    assert q.mocks["trigger.add"].call_count == 2
    log.assert_called_once()
    assert "bad" in q.actions


def test_save_hook_syncs(tmp_path: Path) -> None:
    """The save hook writes both dicts."""
    p = _plugin(tmp_path)
    p.actions["a"] = {"x": 1}
    p.groups["g"] = False
    p._phook_actions_save()
    assert dict(PersistentDict("x", tmp_path / "actions.txt", "c")) == {"a": {"x": 1}}
    assert dict(PersistentDict("x", tmp_path / "groups.txt", "c")) == {"g": False}


def test_uninitialize_removes_owner_triggers(tmp_path: Path) -> None:
    """The uninitialize hook removes every trigger the plugin owns."""
    p = _plugin(tmp_path)
    p._phook_actions_uninitialize()
    p.mocks["trigger.remove.for.owner"].assert_called_once_with(PID)


def _fire(p: Any, name: str, groups: Any, matches: Any, text: str) -> None:
    p.record = {
        "trigger_name": name,
        "groups": groups,
        "matches": matches,
        "line": SimpleNamespace(noansi=text),
    }
    p._trigger_matched()


def test_trigger_matched_runs_parts(tmp_path: Path) -> None:
    """Each part runs through command.line.run, hidden from history, and counts a hit."""
    p = _plugin(tmp_path)
    p._api_action_add("a", r"^(\w+) dies", "stand|kill %1")
    with patch.object(actions_module, "log_to"):
        _fire(p, "a", ("orc",), {}, "orc dies")
    run = p.mocks["command.line.run"]
    assert [c.args[0] for c in run.call_args_list] == ["stand", "kill orc"]
    assert all(c.kwargs == {"show_in_history": False} for c in run.call_args_list)
    assert p.session_hits == {"a": 1}


def test_trigger_matched_skips_disabled_unknown_and_no_record(tmp_path: Path) -> None:
    """A disabled or unknown action, or no record, runs nothing."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "y", enabled=False)
    _fire(p, "a", (), {}, "x")
    _fire(p, "zz", (), {}, "x")
    p.record = None
    p._trigger_matched()
    p.mocks["command.line.run"].assert_not_called()
    assert p.session_hits == {}


def test_trigger_matched_injection_logs_and_runs_nothing(tmp_path: Path) -> None:
    """Matched text that would start a proxy command logs a warning and runs nothing."""
    p = _plugin(tmp_path)
    p._api_action_add("a", r"^(.*)$", "%1")
    with patch.object(actions_module, "log_to") as log:
        _fire(p, "a", ("#bp.x",), {}, "#bp.x")
    p.mocks["command.line.run"].assert_not_called()
    assert log.call_args.args[1] == logging.WARNING
    assert p.session_hits == {}


def test_command_add(tmp_path: Path) -> None:
    """add joins the command, takes flags, and un-doubles the separator in both."""
    args = {
        "name": "k",
        "regex": r"^(a||b) (\w+)",
        "command": ["stand||look|kill", "%2"],
        "group": "g",
        "disabled": True,
        "color": True,
    }
    p = _plugin(tmp_path, args)
    assert p._command_add().success is True
    assert p.actions["k"] == {
        "regex": r"^(a|b) (\w+)",
        "command": "stand|look|kill %2",
        "group": "g",
        "enabled": False,
        "matchcolor": True,
        "send": "execute",
        "id": 1,
        "hits": 0,
    }


def test_api_add_keeps_text_literal(tmp_path: Path) -> None:
    """The API stores what the caller passes; only the typed command unescapes."""
    p = _plugin(tmp_path)
    assert p._api_action_add("p", "a||b", "x||y") is True
    assert p.actions["p"]["regex"] == "a||b"
    assert p.actions["p"]["command"] == "x||y"


def test_command_add_failures(tmp_path: Path) -> None:
    """No command and a bad regex are errors."""
    base = {"name": "k", "regex": "x", "group": "", "disabled": False, "color": False}
    assert _plugin(tmp_path, {**base, "command": []})._command_add().success is False
    bad = _plugin(tmp_path, {**base, "regex": "(", "command": ["y"]})._command_add()
    assert bad.success is False
    assert "could not set k" in str(bad.message)


def test_command_remove(tmp_path: Path) -> None:
    """remove of an unknown action fails, of a known one succeeds."""
    p = _plugin(tmp_path, {"name": "k"})
    result = p._command_remove()
    assert result.success is False
    assert "does not exist" in str(result.message)
    p._api_action_add("k", "x", "y")
    assert p._command_remove().success is True


def test_command_list(tmp_path: Path) -> None:
    """list filters, escapes and reports an empty store, groups and disabled actions."""
    p = _plugin(tmp_path, {"match": ""})
    assert "No actions defined" in str(p._command_list().message)
    p._api_action_add("red", "x", "@r", "g")
    p._api_action_add("blue", "y", "b")
    p._api_action_enabled_set("blue", False)
    assert p._command_list().message == [
        "[2] blue : y -> b (disabled)",
        "[1] red : x -> @@r (group g)",
    ]
    p.api.table["plugins.core.commands:command.current.args.get"] = lambda: {"match": "re"}
    assert p._command_list().message == ["[1] red : x -> @@r (group g)"]


def test_command_enable_disable(tmp_path: Path) -> None:
    """enable and disable work by name or by group, with exactly one given."""
    p = _plugin(tmp_path, {"name": "a", "group": ""})
    p._api_action_add("a", "x", "y", "g")
    assert p._command_disable().success is True
    assert p._api_action_is_enabled("a") is False
    assert p._command_enable().success is True
    table = p.api.table
    key = "plugins.core.commands:command.current.args.get"
    table[key] = lambda: {"name": "", "group": "g"}
    result = p._command_disable()
    assert result.success is True
    assert "1 actions" in str(result.message)
    assert p._command_enable().success is True
    table[key] = lambda: {"name": "", "group": ""}
    assert p._command_enable().success is False
    table[key] = lambda: {"name": "a", "group": "g"}
    assert p._command_disable().success is False
    table[key] = lambda: {"name": "zz", "group": ""}
    assert p._command_enable().success is False


def test_command_show(tmp_path: Path) -> None:
    """show reports the action, and fails for an unknown one."""
    p = _plugin(tmp_path, {"name": "a"})
    assert p._command_show().success is False
    p._api_action_add("a", "x", "y @r", "g")
    p.session_hits["a"] = 3
    p.mocks["trigger.get"].return_value = SimpleNamespace(hits=7)
    message = p._command_show().message
    assert "command       : y @@r" in message
    assert "session hits  : 3" in message
    assert "trigger hits  : 7" in message


def test_plugin_is_discovered() -> None:
    """Discovery finds the plugin under the plugins.client package."""
    plugins_dir = Path(__file__).resolve().parents[4] / "src" / "bastproxy" / "plugins"
    result = imputils.find_packages_and_plugins(plugins_dir, "bastproxy.plugins.")
    ids = [item["plugin_id"] for item in result.plugins]
    assert "bastproxy.plugins.client.actions" in ids
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
    own_names = _command_names(dict(vars(ActionsPlugin)))
    assert {"set", "reset", "save", "help"} <= base_names
    assert own_names == {"add", "remove", "list", "enable", "disable", "show", "toggle"}
    assert not own_names & base_names


@pytest.mark.parametrize(
    ("command", "groups", "expected"),
    [
        ("say %1{t}", ("x%",), "say x%%{t}"),
        ("say %1%2", ("x%", "{t}"), "say x%%{t}"),
        ("say %1", ("%{t}",), "say %%{t}"),
        ("say %1", ("%%{t}",), "say %%%{t}"),
        ("say %1 %{t}", ("a",), "say a %{t}"),
        ("say %1%%{t}", ("a%",), "say a%%%{t}"),
    ],
)
def test_reference_formed_from_matched_text_is_escaped(
    command: str, groups: tuple[str, ...], expected: str
) -> None:
    """A %{ with a character from matched text is escaped; one in the command is not."""
    assert _expand(command, groups) == [expected]


@pytest.mark.parametrize("value", ["-d", "  -d", "--help"])
def test_option_like_value_in_command_part_refuses(value: str) -> None:
    """A value starting with - in a proxy command part refuses the firing."""
    assert _expand("#bp.client.variables.add n %1", (value,)) is None


def test_value_with_inner_dash_in_command_part_runs() -> None:
    """Only a value that starts with - is refused."""
    assert _expand("#bp.client.variables.add n %1", ("a -d",)) == [
        "#bp.client.variables.add n 'a -d'"
    ]


def _expand_alias(command: str, groups: tuple[str, ...]) -> Any:
    return expand_command(
        command,
        groups,
        {},
        "",
        split_regex=SPLIT,
        separator="|",
        prefix="#bp",
        is_alias=lambda word: word in {"bpa", "bpx"},
    )


@pytest.mark.parametrize(
    ("command", "groups"),
    [("%1", ("bpa",)), ("  %1 now", ("bpa",)), ("%1x", ("bp",)), ("%*", ("bpa z",))],
)
def test_alias_named_by_matched_text_refuses(command: str, groups: tuple[str, ...]) -> None:
    """A MUD part whose first word comes from matched text and is an alias refuses."""
    if command == "%*":
        assert (
            expand_command(
                command,
                (),
                {},
                groups[0],
                split_regex=SPLIT,
                separator="|",
                prefix="#bp",
                is_alias=lambda word: word == "bpa",
            )
            is None
        )
    else:
        assert _expand_alias(command, groups) is None


def test_alias_written_in_command_or_later_word_runs() -> None:
    """An alias the action names itself, or matched text after the first word, runs."""
    assert _expand_alias("bpa %1", ("x",)) == ["bpa x"]
    assert _expand_alias("say %1", ("bpa",)) == ["say bpa"]


def test_is_alias_without_aliases_plugin(tmp_path: Path) -> None:
    """With the aliases API missing, no word is an alias."""
    p = _plugin(tmp_path)
    p.api.table["libs.api:api.exists"] = lambda location: False
    assert p._is_alias("bpa") is False
    p.api.table["libs.api:api.exists"] = lambda location: True
    p.api.table["plugins.client.aliases:alias.is.enabled"] = lambda word: word == "bpa"
    assert p._is_alias("bpa") is True
    assert p._is_alias("look") is False
    assert p._is_alias("") is False


def _expand_resends(command: str, groups: tuple[str, ...]) -> Any:
    return expand_command(
        command,
        groups,
        {},
        "",
        split_regex=SPLIT,
        separator="|",
        prefix="#bp",
        alias_resends=lambda text: text.lstrip().startswith("n "),
    )


def test_matched_text_into_a_resent_alias_refuses() -> None:
    """Matched text in a part whose alias is re-sent refuses the firing."""
    assert _expand_resends("n %1", ("x -d",)) is None
    assert _expand_resends("  n say %1", ("x",)) is None


def test_resent_alias_without_matched_text_runs() -> None:
    """A re-sent alias with no matched text, or an empty value, runs as written."""
    assert _expand_resends("n fixed", ()) == ["n fixed"]
    assert _expand_resends("n %1", ("",)) == ["n "]
    assert _expand_resends("k %1", ("orc",)) == ["k orc"]


def test_alias_resends_without_aliases_plugin(tmp_path: Path) -> None:
    """With the aliases API missing, nothing is re-sent; with it, its answer is used."""
    p = _plugin(tmp_path)
    assert p._alias_resends("n x") is False
    p.api.table["libs.api:api.exists"] = lambda location: True
    p.api.table["plugins.client.aliases:alias.expansion.is.resent"] = lambda text: text == "n x"
    assert p._alias_resends("n x") is True
    assert p._alias_resends("k x") is False


def test_expand_matches_prefix_in_any_case() -> None:
    """#782: an upper-case prefix is a command part, and a MUD part may not become one."""
    out = expand_command(
        "#BP.core.x %1", ("a b",), {}, "", split_regex=SPLIT, separator="|", prefix="#bp"
    )
    assert out == ["#BP.core.x 'a b'"]
    assert _expand("%1", ("#BP.x",)) is None


def _expand_escaped(command: str, groups: tuple[str, ...], escape: bool = True) -> Any:
    return expand_command(
        command,
        groups,
        {},
        "",
        split_regex=SPLIT,
        separator="|",
        prefix="#bp",
        escape_command_references=escape,
    )


@pytest.mark.parametrize(
    "command",
    [
        "#bp.client.loop.run 2 %1",  # literal_args, but re-sends its arguments (#816)
        "#bp.client.variables.add n %1",  # literal definition, expands the stored text later
        "#bp.client.aliases.add n %1",
        "#bp.test.go %1",
    ],
)
def test_matched_reference_in_any_command_part_is_escaped(command: str) -> None:
    """#816: matched %{x} never becomes a reference, whatever command the part runs."""
    out = _expand_escaped(command, ("%{x}",))
    assert out == [command.replace("%1", "'%%{x}'")]


def test_literal_definition_stores_escaped_text() -> None:
    """#816: a definition stores %%{x}, which expands later to the literal %{x}."""
    from bastproxy.plugins.client.variables.plugin._variables import expand_references

    out = _expand_escaped("#bp.client.variables.add n %1", ("%{x}",))
    assert out == ["#bp.client.variables.add n '%%{x}'"]
    assert expand_references("'%%{x}'", {"x": "SECRET"}) == "'%{x}'"


def test_own_reference_in_command_part_is_not_escaped() -> None:
    """#816: a %{dest} written in the action's command stays a reference."""
    out = _expand_escaped("#bp.test.go %{dest} %1", ("%{x}",))
    assert out == ["#bp.test.go %{dest} '%%{x}'"]


def test_command_part_not_escaped_without_variables_plugin() -> None:
    """#816: with no variables plugin nothing would undo the escape, so none is done."""
    assert _expand_escaped("#bp.test.go %1", ("%{x}",), escape=False) == ["#bp.test.go '%{x}'"]


def test_no_escape_without_matched_text() -> None:
    """#816: a part with no matched text is left as written."""
    assert _expand_escaped("#bp.test.go %{dest}", ()) == ["#bp.test.go %{dest}"]
    assert _expand_escaped("#bp.test.go %1", ("",)) == ["#bp.test.go ''"]


def test_option_like_refusal_wins_over_escaping() -> None:
    """#816: an option-like value still refuses the firing."""
    assert _expand_escaped("#bp.test.go %1", ("-d %{x}",)) is None


@pytest.mark.parametrize(
    ("loaded", "expected"), [(True, "#bp.t.go '%%{x}'"), (False, "#bp.t.go '%{x}'")]
)
def test_trigger_matched_escapes_when_variables_loaded(
    tmp_path: Path, loaded: bool, expected: str
) -> None:
    """#816: end to end, matched %{x} is escaped only when the variables plugin is loaded."""
    p = _plugin(tmp_path)
    p.api.table["libs.api:api.exists"] = lambda location: loaded
    p._api_action_add("a", r"^(.*)$", "#bp.t.go %1")
    with patch.object(actions_module, "log_to"):
        _fire(p, "a", ("%{x}",), {}, "%{x}")
    assert [c.args[0] for c in p.mocks["command.line.run"].call_args_list] == [expected]
