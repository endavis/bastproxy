# Project: bastproxy
# Filename: tests/plugins/client/aliases/test_aliases_features.py
#
# File Description: Tests for alias prefix matching, ids, toggle, hits and logging
#
# By: Bast
"""Tests for `plugins.client.aliases` (issues #773, #774 audit set: #786-#790)."""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from bastproxy.libs.persistentdict import PersistentDict
from bastproxy.libs.records import UpdateFlag
from bastproxy.plugins.client.aliases.plugin import _aliases as aliases_module

from .test_aliases import _plugin, _run


def _set_args(p: Any, args: dict[str, Any]) -> None:
    p.api.table["plugins.core.commands:command.current.args.get"] = lambda: args


def _map_plugin(tmp_path: Path) -> Any:
    p = _plugin(tmp_path)
    p._api_alias_add("map", "#bp.client.mapper")
    return p


def test_prefix_match_resends_the_tail_on_the_command(tmp_path: Path) -> None:
    """`map.find orc` re-sends `#bp.client.mapper.find orc` (#773)."""
    p = _map_plugin(tmp_path)
    _line, record = _run(p, "map.find orc")
    p.run.assert_called_once_with("#bp.client.mapper.find orc", show_in_history=False)
    assert record.addupdate.call_args.args[0] == UpdateFlag.MODIFY
    assert p.session_hits == {"map": 1}


@pytest.mark.parametrize("text", ["mapper", "maps", "map.", "other.find"])
def test_prefix_match_ignores_near_misses(tmp_path: Path, text: str) -> None:
    """Only `name.` plus at least one character matches."""
    p = _map_plugin(tmp_path)
    line, _ = _run(p, text)
    assert line.line == text
    p.run.assert_not_called()


def test_prefix_match_exact_alias_wins_and_longest_prefix_wins(tmp_path: Path) -> None:
    """An exact alias beats a prefix match; a longer dotted prefix beats a shorter one."""
    p = _map_plugin(tmp_path)
    p._api_alias_add("map.find", "look %*")
    line, _ = _run(p, "map.find orc")
    assert line.line == "look orc"
    p.run.assert_not_called()
    p._api_alias_add("a", "#bp.one")
    p._api_alias_add("a.b", "#bp.two")
    _run(p, "a.b.c x")
    p.run.assert_called_once_with("#bp.two.c x", show_in_history=False)


def test_prefix_match_needs_an_enabled_command_prefix_alias(tmp_path: Path) -> None:
    """A non-command expansion or a disabled alias never prefix-matches."""
    p = _plugin(tmp_path)
    p._api_alias_add("k", "kill %1")
    p._api_alias_add("off", "#bp.x", enabled=False)
    for text in ["k.x orc", "off.x"]:
        line, _ = _run(p, text)
        assert line.line == text
    p.run.assert_not_called()


def test_prefix_match_with_arguments_keeps_tail_on_first_word(tmp_path: Path) -> None:
    """`%1` and `%*` substitute after the tail is attached to the first word."""
    p = _plugin(tmp_path)
    p._api_alias_add("m", "#bp.client.mapper %1")
    _run(p, "m.find orc")
    p.run.assert_called_once_with("#bp.client.mapper.find orc", show_in_history=False)
    p.run.reset_mock()
    p._api_alias_add("n", "#bp.client.mapper -x %*")
    _run(p, "n.find a b")
    p.run.assert_called_once_with("#bp.client.mapper.find -x a b", show_in_history=False)


def test_prefix_match_refuses_percent_in_the_tail(tmp_path: Path) -> None:
    """Typed text is never substituted as an argument reference through the tail."""
    p = _map_plugin(tmp_path)
    line, _ = _run(p, "map.%1 x")
    assert line.line == "map.%1 x"
    p.run.assert_not_called()


def test_expansion_is_resent_for_a_prefix_match(tmp_path: Path) -> None:
    """The actions guard sees a prefix-matched line as re-sent."""
    p = _map_plugin(tmp_path)
    assert p._api_alias_expansion_is_resent("map.find orc") is True
    assert p._api_alias_expansion_is_resent("maps") is False
    assert p.session_hits == {}
    assert p.aliases["map"]["hits"] == 0


def test_command_add_refuses_existing_name_without_overwrite(tmp_path: Path) -> None:
    """add of an existing name needs -o; with -o it replaces and keeps id and hits (#786)."""
    p = _plugin(tmp_path)
    p._api_alias_add("k", "kill")
    p.aliases["k"]["hits"] = 4
    args = {"name": "k", "expansion": ["new"], "group": "", "disabled": False}
    _set_args(p, args)
    result = p._command_add()
    assert result.success is False
    assert result.message == ["alias k exists, use -o to replace it"]
    assert p.aliases["k"]["expansion"] == "kill"
    _set_args(p, {**args, "overwrite": True})
    assert p._command_add().success is True
    assert p.aliases["k"] == {
        "expansion": "new",
        "group": "",
        "enabled": True,
        "id": 1,
        "hits": 4,
    }


def test_hits_count_real_expansions_only_and_persist(tmp_path: Path) -> None:
    """Total hits count real expansions, not probes, and survive a save and reload (#787)."""
    p = _plugin(tmp_path)
    p._api_alias_add("k", "kill %1")
    p._api_alias_expansion_is_resent("k orc")
    assert p.aliases["k"]["hits"] == 0
    _run(p, "k orc")
    _run(p, "k orc")
    assert p.aliases["k"]["hits"] == 2
    assert p.session_hits == {"k": 2}
    p._phook_aliases_save()
    assert PersistentDict("x", tmp_path / "aliases.txt", "c")["k"]["hits"] == 2
    _set_args(p, {"name": "k"})
    message = p._command_show().message
    assert "total hits    : 2" in message
    assert "session hits  : 2" in message


def test_ids_are_sequential_and_never_reused(tmp_path: Path) -> None:
    """Ids start at 1; a removed id is not handed out again, even after a reload (#788)."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "x")
    p._api_alias_add("b", "y")
    assert (p.aliases["a"]["id"], p.aliases["b"]["id"]) == (1, 2)
    p._api_alias_remove("b")
    q = _plugin(tmp_path)
    q._upgrade()
    q._api_alias_add("c", "z")
    assert q.aliases["c"]["id"] == 3
    assert PersistentDict("x", tmp_path / "state.txt", "c")["next_id"] == 4


def test_commands_accept_an_id(tmp_path: Path) -> None:
    """remove, show, enable, disable and toggle accept an id as well as a name (#788)."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "x")
    p._api_alias_add("b", "y")
    _set_args(p, {"name": "2", "group": ""})
    assert p._command_disable().success is True
    assert p.aliases["b"]["enabled"] is False
    assert p._command_toggle().success is True
    assert p.aliases["b"]["enabled"] is True
    assert p._command_toggle().success is True
    assert p.aliases["b"]["enabled"] is False
    assert p._command_enable().success is True
    assert any("alias         : b" in line for line in p._command_show().message)
    assert p._command_remove().success is True
    assert "b" not in p.aliases
    assert p._command_show().success is False


def test_toggle_flips_an_alias_and_a_group(tmp_path: Path) -> None:
    """toggle flips one alias or one group, and needs exactly one of the two."""
    p = _plugin(tmp_path)
    p._api_alias_add("a", "x", "g")
    _set_args(p, {"name": "a", "group": ""})
    assert p._command_toggle().message == ["alias a disabled"]
    assert p._command_toggle().message == ["alias a enabled"]
    _set_args(p, {"name": "", "group": "g"})
    assert p._command_toggle().success is True
    assert p._api_alias_group_is_enabled("g") is False
    assert p._command_toggle().success is True
    assert p._api_alias_group_is_enabled("g") is True
    for args in ({"name": "", "group": ""}, {"name": "a", "group": "g"}):
        _set_args(p, args)
        assert p._command_toggle().success is False
    _set_args(p, {"name": "zz", "group": ""})
    assert p._command_toggle().success is False


def test_digit_only_names_are_refused(tmp_path: Path) -> None:
    """A name made only of digits would be ambiguous with an id (#788)."""
    p = _plugin(tmp_path)
    assert p._api_alias_add("12", "x") is False
    assert dict(p.aliases) == {}


def test_upgrade_old_file(tmp_path: Path) -> None:
    """An old aliases.txt gets ids in sorted order and hits; a digit-named one is kept by id."""
    old = PersistentDict("x", tmp_path / "aliases.txt", "c")
    old["zeta"] = {"expansion": "z", "group": "", "enabled": True}
    old["alpha"] = {"expansion": "a", "group": "", "enabled": True}
    old["12"] = {"expansion": "t", "group": "", "enabled": True}
    old.sync()
    p = _plugin(tmp_path)
    p._upgrade()
    # PersistentDict turns a digit-only key into an int on load and on every set
    assert set(p.aliases) == {"zeta", "alpha", 12}
    assert [p.aliases[name]["id"] for name in (12, "alpha", "zeta")] == [1, 2, 3]
    assert all(item["hits"] == 0 for item in p.aliases.values())
    assert PersistentDict("x", tmp_path / "state.txt", "c")["next_id"] == 4
    assert p._resolve("1") == 12
    assert p._resolve("2") == "alpha"
    assert p._resolve("nope") is None


def test_debug_logging_of_an_expansion(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A real expansion is logged at DEBUG with its name, input and result (#790)."""
    p = _map_plugin(tmp_path)
    p._api_alias_add("k", "kill %1")
    with (
        patch.object(aliases_module, "get_logger", return_value=logging.getLogger("t790.alias")),
        caplog.at_level(logging.DEBUG, logger="t790.alias"),
    ):
        _run(p, "k orc")
        _run(p, "map.find x")
        p._api_alias_expansion_is_resent("k orc")
    messages = [r.getMessage() for r in caplog.records if r.name == "t790.alias"]
    assert len(messages) == 2
    assert "alias k matched by name" in messages[0]
    assert "'k orc'" in messages[0]
    assert "'kill orc'" in messages[0]
    assert "alias map matched by prefix .find" in messages[1]
    assert "'#bp.client.mapper.find x'" in messages[1]
