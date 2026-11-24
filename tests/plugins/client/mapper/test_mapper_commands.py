"""Tests for the mapper commands."""

from typing import Any

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.client.mapper.plugin._mapper import FIND_LIMIT, MapperPlugin
from bastproxy.plugins.core.commands import CommandResult

from .conftest import Harness


def _run(h: Harness, name: str, **args: Any) -> CommandResult:
    defaults: dict[str, dict[str, Any]] = {
        "find": {"text": [], "area": None, "flag": None, "unexplored": False},
        "purge": {"room": None, "area": None},
        "note": {"words": [], "delete": False},
        "showroom": {"uid": None},
    }
    h.args = {**defaults.get(name, {}), **args}
    result = getattr(h.plugin, f"_command_{name}")()
    assert isinstance(result, CommandResult)
    return result


def _text(result: CommandResult) -> str:
    return "\n".join([result.message] if isinstance(result.message, str) else result.message)


def test_find(test_map: Harness) -> None:
    """find by name, area, flag, unexplored, and with no match."""
    test_map.plugin.current_room = "A"
    result = _run(test_map, "find", text=["room", "c"])
    assert "C | Room C | test | 2" in _text(result)
    assert "uid | name" in _text(result)
    assert "F |" not in _text(_run(test_map, "find", text=["room", "c"]))
    assert "B |" in _text(_run(test_map, "find", flag="noportal"))
    assert "A |" in _text(_run(test_map, "find", area="test"))
    unexplored = _text(_run(test_map, "find", unexplored=True))
    assert "E |" in unexplored
    assert "A |" not in unexplored
    assert _text(_run(test_map, "find", text=["zzz"])) == "No rooms found"


def test_find_cap(harness: Harness) -> None:
    """find shows at most 50 rooms."""
    for i in range(FIND_LIMIT + 5):
        harness.plugin._api_room_add({"uid": str(i), "name": "same"})
    text = _text(_run(harness, "find", text=["same"]))
    assert f"showing {FIND_LIMIT}" in text
    assert text.count("same") == FIND_LIMIT


def test_goto(test_map: Harness) -> None:
    """goto sends the whole path; it fails with no current room or no path."""
    assert _run(test_map, "goto", uid="C").success is False
    test_map.plugin.current_room = "A"
    test_map.plugin._api_movement_register(
        "g", lambda steps: ["run " + "".join(s["dir"] for s in steps)]
    )
    assert _run(test_map, "goto", uid="C").success is True
    assert test_map.mud == ["run nn"]
    assert _run(test_map, "goto", uid="nowhere").success is False


def test_walkto_resume_stop(test_map: Harness) -> None:
    """walkto starts, stop stops, resume resumes and fails when idle."""
    p = test_map.plugin
    assert _run(test_map, "walkto", uid="C").success is False
    assert _run(test_map, "resume").success is False
    assert _run(test_map, "stop").success is False
    p.current_room = "A"
    assert _run(test_map, "walkto", uid="C").success is True
    assert test_map.mud == ["n"]
    assert _run(test_map, "stop").success is True
    assert _run(test_map, "resume").success is True
    assert test_map.mud == ["n", "n"]


def test_where_sends_nothing(test_map: Harness) -> None:
    """where shows directions and cost without moving."""
    test_map.plugin.current_room = "A"
    result = _run(test_map, "where", uid="C")
    assert _text(result) == "cost 2: n, n"
    assert test_map.mud == []
    assert _run(test_map, "where", uid="nowhere").success is False


def test_showroom(test_map: Harness) -> None:
    """showroom shows the current room, an explicit uid, and fails for an unknown one."""
    p = test_map.plugin
    assert _run(test_map, "showroom").success is False
    p.current_room = "A"
    p._api_room_note_set("A", "a note")
    text = _text(_run(test_map, "showroom"))
    assert "a note" in text
    assert "n -> B (cost 1)" in text
    assert "D" in _text(_run(test_map, "showroom", uid="D"))
    assert 'requires {"level": 50}' in _text(_run(test_map, "showroom", uid="D"))
    assert _run(test_map, "showroom", uid="zzz").success is False


def test_purge(test_map: Harness) -> None:
    """purge removes a room or an area and needs exactly one option."""
    assert _run(test_map, "purge").success is False
    assert _run(test_map, "purge", room="A", area="test").success is False
    assert _run(test_map, "purge", room="A").success is True
    assert _run(test_map, "purge", room="A").success is False
    result = _run(test_map, "purge", area="test")
    assert "5 rooms" in _text(result)
    assert test_map.plugin._api_room_list() == []


def test_note(test_map: Harness) -> None:
    """note sets, shows and deletes; the uid defaults to the current room."""
    p = test_map.plugin
    assert _run(test_map, "note").success is False
    p.current_room = "A"
    assert _text(_run(test_map, "note")) == "A has no note"
    assert _run(test_map, "note", words=["be", "careful"]).success is True
    assert p._api_room_note_get("A") == "be careful"
    assert _run(test_map, "note", words=["B", "other"]).success is True
    assert p._api_room_note_get("B") == "other"
    assert "other" in _text(_run(test_map, "note", words=["B"]))
    assert _run(test_map, "note", words=["B"], delete=True).success is True
    assert _run(test_map, "note", delete=True, words=["B"]).success is False
    p.current_room = "zzz"
    assert _run(test_map, "note").success is False


def _command_names(methods: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for func in methods.values():
        data = getattr(func, "command_data", None)
        if data is None:
            continue
        name = data.command.get("name") or func.__name__.replace("_command_", " ")
        names.add(name.strip())
    return names


def test_command_names_do_not_shadow_base_plugin_commands() -> None:
    """No mapper command is named like a BasePlugin command."""
    base_names: set[str] = set()
    for klass in BasePlugin.__mro__:
        base_names |= _command_names(dict(vars(klass)))
    own = _command_names(dict(vars(MapperPlugin)))
    assert own == {"find", "goto", "walkto", "resume", "stop", "where", "showroom", "purge", "note"}
    assert not own & base_names
