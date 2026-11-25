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
        "accept": {"uid": None},
        "ignoreexits": {"uid": None, "clear": False},
    }
    h.args = {**defaults.get(name, {}), **args}
    result = getattr(h.plugin, f"_command_{name}")()
    assert isinstance(result, CommandResult)
    return result


def _text(result: CommandResult) -> str:
    return "\n".join([result.message] if isinstance(result.message, str) else result.message)


def _sent(h: Harness) -> str:
    """Return everything sent to the client so far, as one text."""
    return "\n".join(line for msg in h.client for line in ([msg] if isinstance(msg, str) else msg))


def _find_text(h: Harness, **args: Any) -> str:
    """Run find with a current room and return the table the client got."""
    h.client.clear()
    result = _run(h, "find", **args)
    assert "finding the steps" in _text(result)
    return _sent(h)


def test_find(test_map: Harness) -> None:
    """find by name, area, flag, unexplored, and with no match."""
    test_map.plugin.current_room = "A"
    text = _find_text(test_map, text=["room", "c"])
    assert "C | Room C | test | 2" in text
    assert "uid | name" in text
    assert "F |" not in text
    assert "B |" in _find_text(test_map, flag="noportal")
    assert "A |" in _find_text(test_map, area="test")
    unexplored = _find_text(test_map, unexplored=True)
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
    assert "going to C: run nn" in _sent(test_map)
    test_map.client.clear()
    assert _run(test_map, "goto", uid="nowhere").success is True
    assert "no path to nowhere" in _sent(test_map)


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
    test_map.client.clear()
    assert _run(test_map, "walkto", uid="nowhere").success is True
    assert "could not walk to nowhere: no path" in _sent(test_map)


def test_where_sends_nothing(test_map: Harness) -> None:
    """where shows directions and cost without moving."""
    test_map.plugin.current_room = "A"
    assert _run(test_map, "where", uid="C").success is True
    assert "cost 2: n, n" in _sent(test_map)
    assert test_map.mud == []
    test_map.client.clear()
    assert _run(test_map, "where", uid="nowhere").success is True
    assert "no path to nowhere" in _sent(test_map)
    p = test_map.plugin
    p.current_room = None
    assert _run(test_map, "where", uid="C").success is False


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
    assert own == {
        "find",
        "goto",
        "walkto",
        "resume",
        "stop",
        "where",
        "showroom",
        "purge",
        "note",
        "accept",
        "ignoreexits",
    }
    assert not own & base_names


# ---- accept and ignoreexits (#796, #797) ----


def test_accept(test_map: Harness) -> None:
    """accept applies the held area and exits and removes stale plain exits."""
    p = test_map.plugin
    assert _run(test_map, "accept").success is False  # no current room
    p.current_room = "A"
    assert _run(test_map, "accept").success is False  # nothing held
    p._api_exit_add("A", "n", "B", 3, {"level": 100})
    p._api_room_add({"uid": "A", "area": "other", "exits": {"n": "C", "enter portal": "C"}})
    test_map.events.clear()
    assert _run(test_map, "accept").success is True
    room = p.store.get_room("A")
    assert room is not None
    assert room["area"] == "other"
    moved = p.store.get_exit("A", "n")
    assert moved is not None
    assert (moved.touid, moved.cost, moved.requirement) == ("C", 3, {"level": 100})
    assert p.store.get_exit("A", "s") is None
    assert all(e.dir != "s" for e in p.graph.exits_from("A"))
    assert p.store.get_exit("A", "enter portal") is not None
    assert "room_mismatch" not in test_map.names()
    assert _run(test_map, "accept").success is False


def test_accept_keeps_custom_exit(test_map: Harness) -> None:
    """A custom exit missing from the update survives accept."""
    p = test_map.plugin
    p._api_room_add({"uid": "A", "area": "other", "exits": {"n": "B", "s": "E"}})
    assert _run(test_map, "accept", uid="A").success is True
    assert p.store.get_exit("A", "enter portal") is not None


def test_ignoreexits_command(test_map: Harness) -> None:
    """ignoreexits sets and clears the flag, and a flagged room is not compared."""
    p = test_map.plugin
    assert _run(test_map, "ignoreexits").success is False  # no current room
    assert _run(test_map, "ignoreexits", uid="zz").success is False
    p.current_room = "A"
    assert _run(test_map, "ignoreexits").success is True
    room = p.store.get_room("A")
    assert room is not None
    assert "ignoreexits" in room["flags"]
    test_map.events.clear()
    p._api_room_add({"uid": "A", "area": "test", "exits": {"n": "C"}})
    assert "room_mismatch" not in test_map.names()
    assert _run(test_map, "ignoreexits", uid="B").success is True
    assert "ignoreexits" in p.graph.room_flags("B")
    assert _run(test_map, "ignoreexits", clear=True).success is True
    room = p.store.get_room("A")
    assert room is not None
    assert "ignoreexits" not in room["flags"]
