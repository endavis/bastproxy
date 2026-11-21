# Project: bastproxy
# Filename: tests/plugins/client/variables/test_variables.py
#
# File Description: Tests for the variables plugin
#
# By: Bast
"""Unit tests for `plugins.client.variables` (issue #707)."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.plugins import imputils
from bastproxy.libs.records import UpdateFlag
from bastproxy.libs.records.rtypes.networkdata import NetworkDataLine
from bastproxy.plugins.client.variables.plugin._variables import (
    EXPAND_PRIORITY,
    VariablesPlugin,
    expand_references,
)

V = {"t": "orc", "w": "sword", "empty": "", "nest": "%{t}"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("kill %{t}", "kill orc"),
        ("%{t} and %{w}", "orc and sword"),
        ("%{w}s", "swords"),
        ("%{nope}", "%{nope}"),
        ("%%{t}", "%{t}"),
        ("%%{nope}", "%{nope}"),
        ("100%%", "100%%"),
        ("%%{ x", "%%{ x"),
        ("%{nest}", "%{t}"),
        ("a%{empty}b", "ab"),
        ("%{T}", "%{T}"),
        ("%{1x}", "%{1x}"),
    ],
)
def test_expand_references(text: str, expected: str) -> None:
    """References expand in a single pass, with the escape and unknown names kept."""
    assert expand_references(text, V) == expected


def _stub(tmp_path: Path) -> Any:
    stub = MagicMock()
    stub.plugin_id = "plugins.client.variables"
    stub.variables = PersistentDict("x", tmp_path / "variables.txt", "c")
    return stub


def test_set_get_exists_remove_list(tmp_path: Path) -> None:
    """The API stores, reads and removes values; list returns a copy."""
    stub = _stub(tmp_path)
    assert VariablesPlugin._api_variable_set(stub, "t", "orc") is True
    assert VariablesPlugin._api_variable_get(stub, "t") == "orc"
    assert VariablesPlugin._api_variable_get(stub, "x") is None
    assert VariablesPlugin._api_variable_exists(stub, "t") is True
    listed = VariablesPlugin._api_variable_list(stub)
    listed["z"] = "1"
    assert VariablesPlugin._api_variable_exists(stub, "z") is False
    assert VariablesPlugin._api_variable_reference_to_value(stub, "%{t}") == "orc"
    assert VariablesPlugin._api_variable_remove(stub, "t") is True
    assert VariablesPlugin._api_variable_remove(stub, "t") is False


@pytest.mark.parametrize(
    ("name", "value"),
    [("1x", "a"), ("a-b", "a"), ("", "a"), ("a", 5), ("a", "x\ny"), ("a", "x\ry")],
)
def test_set_refuses_bad_input(tmp_path: Path, name: str, value: Any) -> None:
    """A bad name or value is refused and nothing is stored."""
    stub = _stub(tmp_path)
    assert VariablesPlugin._api_variable_set(stub, name, value) is False
    assert dict(stub.variables) == {}


def test_persistence(tmp_path: Path) -> None:
    """Values survive a new PersistentDict on the same file, also after a remove."""
    stub = _stub(tmp_path)
    VariablesPlugin._api_variable_set(stub, "a", "1")
    VariablesPlugin._api_variable_set(stub, "b", "2")
    assert dict(PersistentDict("x", tmp_path / "variables.txt", "c")) == {"a": "1", "b": "2"}
    VariablesPlugin._api_variable_remove(stub, "a")
    assert dict(PersistentDict("x", tmp_path / "variables.txt", "c")) == {"b": "2"}


def _cmd_stub(tmp_path: Path, args: dict[str, Any]) -> Any:
    stub = _stub(tmp_path)
    escape = MagicMock(side_effect=lambda s: s.replace("@", "@@"))

    def api(name: str) -> Any:
        if name == "plugins.core.commands:command.current.args.get":
            return lambda: args
        if name == "plugins.core.colors:colorcode.escape":
            return escape
        if name == "plugins.client.variables:variable.set":
            return lambda n, v: VariablesPlugin._api_variable_set(stub, n, v)
        if name == "plugins.client.variables:variable.remove":
            return lambda n: VariablesPlugin._api_variable_remove(stub, n)
        raise AssertionError(name)

    stub.api = api
    stub.escape = escape
    return stub


def test_command_add_joins_value(tmp_path: Path) -> None:
    """A multi-word value is joined with spaces."""
    stub = _cmd_stub(tmp_path, {"name": "t", "value": ["a", "big", "orc"]})
    result = VariablesPlugin._command_add(stub)
    assert result.success is True
    assert stub.variables["t"] == "a big orc"


def test_command_add_without_value_fails(tmp_path: Path) -> None:
    """No value is an error."""
    stub = _cmd_stub(tmp_path, {"name": "t", "value": []})
    assert VariablesPlugin._command_add(stub).success is False


def test_command_remove_unknown_fails(tmp_path: Path) -> None:
    """Removing an unknown variable fails with a message."""
    stub = _cmd_stub(tmp_path, {"name": "t"})
    result = VariablesPlugin._command_remove(stub)
    assert result.success is False
    assert "does not exist" in str(result.message)


def test_command_list(tmp_path: Path) -> None:
    """List filters by match, escapes colour codes and reports an empty store."""
    stub = _cmd_stub(tmp_path, {"match": ""})
    assert "No variables defined" in str(VariablesPlugin._command_list(stub).message)
    VariablesPlugin._api_variable_set(stub, "red", "@r")
    VariablesPlugin._api_variable_set(stub, "blue", "b")
    result = VariablesPlugin._command_list(stub)
    assert result.message == ["blue : b", "red : @@r"]
    stub.escape.assert_any_call("@r")
    stub2 = _cmd_stub(tmp_path, {"match": "re"})
    assert VariablesPlugin._command_list(stub2).message == ["red : @@r"]


def _run(line: NetworkDataLine, tmp_path: Path, record: Any = "default") -> MagicMock:
    stub = _stub(tmp_path)
    stub.variables["t"] = "orc"
    event_record = MagicMock()
    event_record.__getitem__.side_effect = lambda key: line
    rec = event_record if record == "default" else record

    def api(name: str) -> Any:
        if name == "plugins.core.events:event.current.record.get":
            return lambda: rec
        if name == "plugins.core.commands:command.prefix.get":
            return lambda: "#bp"
        raise AssertionError(name)

    stub.api = api
    VariablesPlugin._eventcb_expand_line(stub)
    return event_record


def test_callback_expands_client_line(tmp_path: Path) -> None:
    """A client line is expanded and the change recorded."""
    line = NetworkDataLine("kill %{t}", originated="client")
    record = _run(line, tmp_path)
    assert line.line == "kill orc"
    assert line.line_modified is True
    record.addupdate.assert_called_once()
    assert record.addupdate.call_args.args[0] == UpdateFlag.MODIFY


def test_callback_undefined_unchanged(tmp_path: Path) -> None:
    """An undefined reference leaves the line and the record alone."""
    line = NetworkDataLine("kill %{x}", originated="client")
    record = _run(line, tmp_path)
    assert line.line == "kill %{x}"
    record.addupdate.assert_not_called()


@pytest.mark.parametrize("text", ["#bp.client.variables.add a %{t}", "  #bp x %{t}"])
def test_callback_skips_command_lines(tmp_path: Path, text: str) -> None:
    """Command-prefix lines are not expanded."""
    line = NetworkDataLine(text, originated="client")
    _run(line, tmp_path)
    assert line.line == text


def test_callback_skips_masked_line(tmp_path: Path) -> None:
    """A line typed with echo off is not expanded."""
    line = NetworkDataLine("pw %{t}", originated="client")
    line.mask_log = True
    _run(line, tmp_path)
    assert line.line == "pw %{t}"


def test_callback_skips_unsent_line(tmp_path: Path) -> None:
    """A line that will not be sent is not expanded."""
    line = NetworkDataLine("a %{t}", originated="client")
    line.send = False
    _run(line, tmp_path)
    assert line.line == "a %{t}"


def test_callback_skips_non_io_line(tmp_path: Path) -> None:
    """A line that is not I/O is not expanded."""
    line = NetworkDataLine("a %{t}", originated="client", line_type="COMMAND-TELNET")
    _run(line, tmp_path)
    assert line.line == "a %{t}"


def test_callback_without_record_returns(tmp_path: Path) -> None:
    """A missing event record returns quietly."""
    line = NetworkDataLine("a %{t}", originated="client")
    _run(line, tmp_path, record=None)
    assert line.line == "a %{t}"


def test_callback_priority_after_commands() -> None:
    """The expansion callback registers at priority 60, after commands (50)."""
    args = VariablesPlugin._eventcb_expand_line.event_registration
    assert args == [{"event_name": "ev_to_mud_data_modify", "priority": EXPAND_PRIORITY}]
    assert EXPAND_PRIORITY > 50


def test_plugin_is_discovered() -> None:
    """Discovery finds the plugin under the plugins.client package."""
    plugins_dir = Path(__file__).resolve().parents[4] / "src" / "bastproxy" / "plugins"
    result = imputils.find_packages_and_plugins(plugins_dir, "bastproxy.plugins.")
    ids = [item["plugin_id"] for item in result.plugins]
    assert "bastproxy.plugins.client.variables" in ids
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
    own_names = _command_names(dict(vars(VariablesPlugin)))

    assert "set" in base_names
    assert own_names == {"add", "remove", "list"}
    assert not own_names & base_names
