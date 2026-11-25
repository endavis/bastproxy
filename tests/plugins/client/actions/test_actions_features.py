# Project: bastproxy
# Filename: tests/plugins/client/actions/test_actions_features.py
#
# File Description: Tests for action send targets, %c, ids, toggle, hits and logging
#
# By: Bast
"""Tests for `plugins.client.actions` (issues #774, #786-#790)."""

import logging
import shlex
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from bastproxy.libs import argp
from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.plugins.client.actions.plugin import _actions as actions_module
from bastproxy.plugins.client.actions.plugin._actions import expand_command, expand_text

from .test_actions import SPLIT, _plugin


def _set_args(p: Any, args: dict[str, Any]) -> None:
    p.api.table["plugins.core.commands:command.current.args.get"] = lambda: args


def _fire(p: Any, name: str, groups: Any, text: str, colorcoded: str | None = None) -> list[str]:
    """Fire an action; return the names of the colorcoded reads (a list holding 0 or 1 item)."""
    reads: list[str] = []

    class Line:
        noansi = text

        @property
        def colorcoded(self) -> str:
            reads.append("read")
            return colorcoded if colorcoded is not None else text

    p.record = {"trigger_name": name, "groups": groups, "matches": {}, "line": Line()}
    p._trigger_matched()
    return reads


def _patched() -> Any:
    client = patch.object(actions_module, "SendDataDirectlyToClient")
    mud = patch.object(actions_module, "SendDataDirectlyToMud")
    return client, mud


def test_send_client_substitutes_without_parsing(tmp_path: Path) -> None:
    """`client` sends one text to all clients, `@` in values doubled, nothing to the MUD."""
    p = _plugin(tmp_path)
    assert p._api_action_add("a", r"^(.*) says (.*)$", "<%1> got #bp.x|%2", send="client")
    client, mud = _patched()
    with client as to_client, mud as to_mud:
        _fire(p, "a", ("@rBob", "hi\r\n@g"), "line")
    to_client.assert_called_once()
    data = to_client.call_args.args[0]
    assert [str(line.line) for line in data] == ["<@@rBob> got #bp.x|hi@@g"]
    assert to_client.call_args.kwargs == {}
    to_client.return_value.assert_called_once_with()
    to_mud.assert_not_called()
    p.mocks["command.line.run"].assert_not_called()
    assert p.session_hits == {"a": 1}
    assert p.actions["a"]["hits"] == 1


def test_send_mud_sends_raw_text(tmp_path: Path) -> None:
    """`mud` sends the text unsplit and unparsed, even if a value starts with the prefix."""
    p = _plugin(tmp_path)
    assert p._api_action_add("a", r"^(.*)$", "say %1|%%1 %{t}", send="mud")
    client, mud = _patched()
    with client as to_client, mud as to_mud:
        _fire(p, "a", ("#bp.x@g\n",), "line")
    to_mud.assert_called_once()
    data = to_mud.call_args.args[0]
    assert [str(line.line) for line in data] == ["say #bp.x@g|%1 %{t}"]
    to_mud.return_value.assert_called_once_with()
    to_client.assert_not_called()
    p.mocks["command.line.run"].assert_not_called()


def test_execute_is_the_default_and_bad_send_is_refused(tmp_path: Path) -> None:
    """A default action runs commands; an unknown send value stores nothing."""
    p = _plugin(tmp_path)
    assert p._api_action_add("a", "x", "look")
    assert p.actions["a"]["send"] == "execute"
    assert p._api_action_add("b", "x", "look", send="tcp") is False
    assert "b" not in p.actions
    client, mud = _patched()
    with client as to_client, mud as to_mud:
        _fire(p, "a", (), "x")
    p.mocks["command.line.run"].assert_called_once()
    to_client.assert_not_called()
    to_mud.assert_not_called()


def test_command_add_takes_send(tmp_path: Path) -> None:
    """-s stores the target; the default is execute."""
    args = {
        "name": "k",
        "regex": "x",
        "command": ["hi"],
        "group": "",
        "disabled": False,
        "color": False,
        "send": "client",
    }
    p = _plugin(tmp_path, args)
    assert p._command_add().success is True
    assert p.actions["k"]["send"] == "client"
    args2 = {k: v for k, v in args.items() if k != "send"}
    other = tmp_path / "other"
    other.mkdir()
    q = _plugin(other, args2)
    assert q._command_add().success is True
    assert q.actions["k"]["send"] == "execute"


def test_color_reference_in_each_target(tmp_path: Path) -> None:
    """%c is the colour-coded line: raw for client, `@` doubled in MUD parts, quoted in commands."""
    colored = "@rred@w text"
    assert (
        expand_text("%c|%1", ("a@b",), {}, "plain", colored, escape_at=True) == "@rred@w text|a@@b"
    )
    assert expand_text("say %c", (), {}, "plain", colored, escape_at=False) == "say @rred@w text"
    parts = expand_command(
        "say %c|#bp.client.actions.show %c",
        (),
        {},
        "plain",
        split_regex=SPLIT,
        separator="|",
        prefix="#bp",
        colorline=colored,
    )
    assert parts == ["say @@rred@@w text", "#bp.client.actions.show '@rred@w text'"]


def test_escaped_color_reference_is_literal() -> None:
    """%%c stays a literal %c in both expanders."""
    assert expand_text("say %%c", (), {}, "p", "@rX", escape_at=True) == "say %c"
    parts = expand_command(
        "say %%c", (), {}, "p", split_regex=None, separator="", prefix="#bp", colorline="@rX"
    )
    assert parts == ["say %c"]


def test_color_is_read_only_when_referenced(tmp_path: Path) -> None:
    """colorcoded is not read unless the command has %c."""
    p = _plugin(tmp_path)
    p._api_action_add("plain", "x", "look")
    p._api_action_add("col", "x", "echo %c", send="client")
    assert _fire(p, "plain", (), "x") == []
    client, _mud = _patched()
    with client as to_client, _mud:
        assert _fire(p, "col", (), "x", colorcoded="@rx") == ["read"]
    assert [str(line.line) for line in to_client.call_args.args[0]] == ["echo @rx"]


def test_color_reference_fits_any_regex(tmp_path: Path) -> None:
    """%c needs no group in the regex."""
    p = _plugin(tmp_path)
    assert p._api_action_add("a", "x", "say %c") is True
    assert p._api_action_add("b", "x", "say %1") is False


def test_command_add_refuses_existing_name_without_overwrite(tmp_path: Path) -> None:
    """add of an existing name needs -o; with -o it replaces and keeps id and hits (#786)."""
    p = _plugin(tmp_path)
    p._api_action_add("k", "x", "look")
    p.actions["k"]["hits"] = 4
    args = {
        "name": "k",
        "regex": "y",
        "command": ["new"],
        "group": "",
        "disabled": False,
        "color": False,
    }
    _set_args(p, args)
    result = p._command_add()
    assert result.success is False
    assert result.message == ["action k exists, use -o to replace it"]
    assert p.actions["k"]["command"] == "look"
    _set_args(p, {**args, "overwrite": True})
    assert p._command_add().success is True
    assert p.actions["k"]["command"] == "new"
    assert (p.actions["k"]["id"], p.actions["k"]["hits"]) == (1, 4)


def test_hits_count_matches_and_persist(tmp_path: Path) -> None:
    """Total hits count real runs, survive a save and reload and show next to session hits."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "look")
    _fire(p, "a", (), "x")
    _fire(p, "a", (), "x")
    assert p.actions["a"]["hits"] == 2
    p._phook_actions_save()
    assert PersistentDict("x", tmp_path / "actions.txt", "c")["a"]["hits"] == 2
    _set_args(p, {"name": "a"})
    message = p._command_show().message
    assert "total hits    : 2" in message
    assert "session hits  : 2" in message
    assert "send          : execute" in message


def test_ids_toggle_and_digit_names(tmp_path: Path) -> None:
    """Ids are sequential and never reused; commands take an id; toggle syncs the trigger."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "look", "g")
    p._api_action_add("b", "y", "look")
    assert (p.actions["a"]["id"], p.actions["b"]["id"]) == (1, 2)
    assert p._api_action_add("12", "x", "look") is False
    p._api_action_remove("b")
    p._api_action_add("c", "z", "look")
    assert p.actions["c"]["id"] == 3
    toggle = p.mocks["trigger.toggle.enable"]
    _set_args(p, {"name": "1", "group": ""})
    assert p._command_toggle().message == ["action a disabled"]
    assert toggle.call_args.args == ("a", False)
    assert p._command_toggle().message == ["action a enabled"]
    assert toggle.call_args.args == ("a", True)
    _set_args(p, {"name": "", "group": "g"})
    assert p._command_toggle().success is True
    assert p._api_action_group_is_enabled("g") is False
    assert toggle.call_args.args == ("a", False)
    for args in ({"name": "", "group": ""}, {"name": "a", "group": "g"}):
        _set_args(p, args)
        assert p._command_toggle().success is False
    _set_args(p, {"name": "zz", "group": ""})
    assert p._command_toggle().success is False
    _set_args(p, {"name": "3", "group": ""})
    assert any("action        : c" in line for line in p._command_show().message)
    assert p._command_remove().success is True
    assert "c" not in p.actions


def test_upgrade_old_file(tmp_path: Path) -> None:
    """An old actions.txt loads as `execute`, with hits and ids in sorted name order."""
    old = PersistentDict("x", tmp_path / "actions.txt", "c")
    for name in ("zeta", "alpha"):
        old[name] = {"regex": "x", "command": "look", "group": "", "enabled": True}
    old.sync()
    p = _plugin(tmp_path)
    p._upgrade()
    assert [p.actions[name]["id"] for name in ("alpha", "zeta")] == [1, 2]
    assert all(i["send"] == "execute" and i["hits"] == 0 for i in p.actions.values())
    assert PersistentDict("x", tmp_path / "state.txt", "c")["next_id"] == 3
    assert PersistentDict("x", tmp_path / "actions.txt", "c")["alpha"]["send"] == "execute"


def test_debug_logging_of_a_match_and_sends(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A match and each send are logged at DEBUG (#790)."""
    p = _plugin(tmp_path)
    p._api_action_add("a", "x", "stand|look")
    p._api_action_add("c", "x", "hi %*", send="client")
    logger = logging.getLogger("t790.action")
    client, mud = _patched()
    with (
        patch.object(actions_module, "get_logger", return_value=logger),
        caplog.at_level(logging.DEBUG, logger="t790.action"),
        client,
        mud,
    ):
        _fire(p, "a", (), "x")
        _fire(p, "c", (), "x")
    messages = [r.getMessage() for r in caplog.records if r.name == "t790.action"]
    assert messages == [
        "action a matched: 'x'",
        "action a sends to execute: 'stand'",
        "action a sends to execute: 'look'",
        "action c matched: 'x'",
        "action c sends to client: 'hi x'",
    ]


def test_empty_command_is_allowed_only_for_mud(tmp_path: Path) -> None:
    """An empty or blank command is stored as empty for `mud` and refused otherwise (#808)."""
    p = _plugin(tmp_path)
    assert p._api_action_add("m", "x", "", send="mud") is True
    assert p.actions["m"]["command"] == ""
    assert p._api_action_add("w", "x", "   ", send="mud") is True
    assert p.actions["w"]["command"] == ""
    for send in ("execute", "client"):
        assert p._api_action_add(f"n_{send}", "x", "", send=send) is False
        assert p._api_action_add(f"b_{send}", "x", "  ", send=send) is False
        assert f"n_{send}" not in p.actions
        assert f"b_{send}" not in p.actions
    assert p._api_action_add("l", "x", "a\nb", send="mud") is False


def test_empty_mud_action_sends_one_empty_line(tmp_path: Path) -> None:
    """Firing an empty `mud` action sends one empty line, not zero (#808)."""
    p = _plugin(tmp_path)
    assert p._api_action_add("m", "x", "", send="mud")
    client, mud = _patched()
    with client as to_client, mud as to_mud:
        _fire(p, "m", (), "x")
    to_client.assert_not_called()
    to_mud.assert_called_once()
    assert [str(line.line) for line in to_mud.call_args.args[0]] == [""]
    assert p.session_hits == {"m": 1}


def test_command_add_empty_command(tmp_path: Path) -> None:
    """add accepts `""` with -s mud, and refuses it for execute and client (#808)."""
    base = {"regex": "x", "group": "", "disabled": False, "color": False, "command": [""]}
    p = _plugin(tmp_path, {**base, "name": "m", "send": "mud"})
    assert p._command_add().success is True
    assert p.actions["m"]["command"] == ""
    assert p.actions["m"]["send"] == "mud"
    for send in ("execute", "client"):
        sub = tmp_path / send
        sub.mkdir()
        q = _plugin(sub, {**base, "name": "n", "send": send})
        result = q._command_add()
        assert result.success is False
        assert "empty only with -s mud" in str(result.message)
        assert "n" not in q.actions
    nothing = _plugin(tmp_path, {**base, "name": "z", "send": "mud", "command": []})
    assert nothing._command_add().success is False


def test_typed_empty_quotes_reach_the_add_command(tmp_path: Path) -> None:
    """The documented syntax `add m "regex" "" -s mud` parses to an empty command word (#808)."""
    parser = argp.ArgumentParser(add_help=False)
    parser.add_argument("-s", "--send", default="execute")
    parser.add_argument("name")
    parser.add_argument("regex")
    parser.add_argument("command", nargs="*")
    parsed = parser.parse_args(shlex.split('-s mud m "\\[ Press Return" ""'))
    assert parsed.command == [""]
    p = _plugin(tmp_path, {**vars(parsed), "group": "", "disabled": False, "color": False})
    assert p._command_add().success is True
    assert p.actions["m"]["command"] == ""
