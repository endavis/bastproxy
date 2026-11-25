"""Tests for the mapper commands."""

import argparse
from typing import Any

from bastproxy.plugins._baseplugin import BasePlugin
from bastproxy.plugins.client.mapper.plugin._mapper import FIND_LIMIT, MapperPlugin
from bastproxy.plugins.core.commands import CommandResult

from .conftest import Harness


def _run(h: Harness, name: str, **args: Any) -> CommandResult:
    defaults: dict[str, dict[str, Any]] = {
        "find": {
            "text": [],
            "area": None,
            "exact": False,
            "flag": None,
            "unexplored": False,
        },
        "walkto": {"portals": False},
        "next": {"index": None, "portals": False},
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
        "next",
        "speedwalk",
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


# ---- walkto without portals, next, exact find, speedwalk, find defaults (#798-#800) ----


def _parser(command: Any) -> argparse.ArgumentParser:
    """Build the argparse parser of a command from its declared arguments."""
    parser = argparse.ArgumentParser()
    for arg in command.command_data.arguments:
        parser.add_argument(*arg["args"], **arg["kwargs"])
    return parser


def test_walkto_avoids_portals_unless_asked(test_map: Harness) -> None:
    """walkto does not use the exits from ``*``; ``-p`` does; goto always does (#798)."""
    p = test_map.plugin
    p.current_room = "A"
    assert _run(test_map, "walkto", uid="F").success is True
    assert "could not walk to F: no path" in _sent(test_map)
    assert test_map.mud == []
    assert _run(test_map, "walkto", uid="F", portals=True).success is True
    assert test_map.mud == ["portal f"]
    p.walk.finish()
    test_map.mud.clear()
    assert _run(test_map, "goto", uid="F").success is True
    assert test_map.mud == ["portal f"]


def test_walk_keeps_its_options_on_reroute_and_resume(test_map: Harness) -> None:
    """A reroute and a resume search the way the walk started, so no recall (#798)."""
    p = test_map.plugin
    p.current_room = "A"
    _run(test_map, "walkto", uid="C")
    assert test_map.mud == ["n"]
    p._api_room_current_set("E")  # an unexpected room: the reroute may not recall
    assert test_map.mud == ["n"]
    assert test_map.event("walk_failed")["reason"] == "unexpected room"
    p.current_room = "A"
    test_map.mud.clear()
    _run(test_map, "walkto", uid="C")
    _run(test_map, "stop")
    p.current_room = "E"
    assert _run(test_map, "resume").success is True
    assert "recall" not in test_map.mud
    assert test_map.event("walk_failed")["reason"] == "no path"


def test_next_needs_a_find_result(test_map: Harness) -> None:
    """next fails before any find (#799)."""
    test_map.plugin.current_room = "A"
    result = _run(test_map, "next")
    assert result.success is False
    assert "find" in _text(result)


def test_next_walks_the_last_find(test_map: Harness) -> None:
    """next walks the entries in order, ``next N`` jumps, and the end fails (#799)."""
    p = test_map.plugin
    p.current_room = "A"
    _find_text(test_map, text=["room", "c"])
    assert p.last_find == ["C"]
    assert _run(test_map, "next").success is True
    assert test_map.mud == ["n"]
    p.walk.finish()
    result = _run(test_map, "next")
    assert result.success is False
    assert "no more rooms" in _text(result)
    test_map.mud.clear()
    assert _run(test_map, "next", index=1).success is True
    assert test_map.mud == ["n"]
    assert p.last_find_next == 1
    for bad in (0, 2):
        failed = _run(test_map, "next", index=bad)
        assert failed.success is False
        assert "1 to 1" in _text(failed)


def test_next_with_unknown_current_room_keeps_the_pointer(test_map: Harness) -> None:
    """next fails with no current room and leaves the pointer where it was (#799)."""
    p = test_map.plugin
    p.last_find = ["C", "D"]
    p.last_find_next = 1
    assert _run(test_map, "next").success is False
    assert p.last_find_next == 1


def test_next_avoids_portals_unless_asked(test_map: Harness) -> None:
    """next walks like walkto: ``-p`` allows the portal exits (#799)."""
    p = test_map.plugin
    p.current_room = "A"
    p.last_find = ["F"]
    _run(test_map, "next")
    assert test_map.mud == []
    assert _run(test_map, "next", index=1, portals=True).success is True
    assert test_map.mud == ["portal f"]


def test_find_without_match_keeps_the_last_result(test_map: Harness) -> None:
    """A find with no match leaves last_find alone (#799)."""
    p = test_map.plugin
    p.current_room = "A"
    _find_text(test_map, text=["room", "c"])
    assert _text(_run(test_map, "find", text=["zzz"])) == "No rooms found"
    assert p.last_find == ["C"]


def test_find_exact(test_map: Harness) -> None:
    """find -e matches the whole name; it needs text (#799)."""
    p = test_map.plugin
    p._api_room_add({"uid": "X", "name": "Room C annex", "area": "test"})
    p.current_room = "A"
    text = _find_text(test_map, text=["room", "c"], exact=True)
    assert "Room C |" in text
    assert "annex" not in text
    assert _run(test_map, "find", exact=True).success is False


def test_speedwalk(test_map: Harness) -> None:
    """speedwalk prints the compressed path and sends nothing to the MUD (#799)."""
    p = test_map.plugin
    p._api_exit_add("D", "climb tree", "F")
    assert _run(test_map, "speedwalk", start="A", target="D").success is True
    assert "A to D, cost 3: 2ne" in _sent(test_map)
    test_map.client.clear()
    _run(test_map, "speedwalk", start="A", target="F")
    assert "A to F, cost 1: portal f" in _sent(test_map)
    test_map.client.clear()
    _run(test_map, "speedwalk", start="A", target="A")
    assert "already there" in _sent(test_map)
    assert test_map.mud == []
    assert _run(test_map, "speedwalk", start="nope", target="A").success is False
    assert _run(test_map, "speedwalk", start="A", target="nope").success is False


def test_speedwalk_separates_custom_exits(harness: Harness) -> None:
    """A custom exit is a segment of its own, joined by the command separator (#799)."""
    p = harness.plugin
    for uid in "ABCDE":
        p._api_room_add({"uid": uid, "name": uid, "area": "t"})
    p._api_exit_add("A", "n", "B")
    p._api_exit_add("B", "n", "C")
    p._api_exit_add("C", "enter portal", "D")
    p._api_exit_add("D", "e", "E")
    _run(harness, "speedwalk", start="A", target="E")
    assert "A to E, cost 4: 2n|enter portal|e" in _sent(harness)
    harness.client.clear()
    p.api.command_separator = ";"
    _run(harness, "speedwalk", start="A", target="E")
    assert "2n;enter portal;e" in _sent(harness)


def _area_map(h: Harness) -> None:
    p = h.plugin
    p._api_room_add({"uid": "Z", "name": "Room Z", "area": "other"})
    p._api_exit_add("Z", "n", "-1")
    p.current_room = "A"


def test_find_area_defaults_to_the_current_area(test_map: Harness) -> None:
    """A bare -a searches the current room's area, also with -u (#800)."""
    _area_map(test_map)
    text = _find_text(test_map, text=["room"], area="")
    assert "Room A" in text
    assert "Room Z" not in text
    unexplored = _find_text(test_map, area="", unexplored=True)
    assert "Room E" in unexplored
    assert "Room Z" not in unexplored
    test_map.plugin.current_room = None
    result = _run(test_map, "find", text=["room"], area="")
    assert result.success is False
    assert "current area is not known" in _text(result)


def test_find_arguments_parse() -> None:
    """The find options: a bare -a, -e, and no -a at all (#799, #800)."""
    from bastproxy.plugins.client.mapper.plugin._mapper import MapperPlugin

    parser = _parser(MapperPlugin._command_find)
    assert parser.parse_args(["-a"]).area == ""
    parsed = parser.parse_args(["room", "-a"])
    assert (parsed.area, parsed.text) == ("", ["room"])
    assert parser.parse_args(["-a", "x"]).area == "x"
    assert parser.parse_args([]).area is None
    assert parser.parse_args(["-e", "Room", "C"]).exact is True


def test_walk_command_arguments_parse() -> None:
    """walkto -p, next [index] -p and speedwalk's two positionals (#798, #799)."""
    from bastproxy.plugins.client.mapper.plugin._mapper import MapperPlugin

    assert _parser(MapperPlugin._command_walkto).parse_args(["C", "-p"]).portals is True
    assert _parser(MapperPlugin._command_walkto).parse_args(["C"]).portals is False
    nxt = _parser(MapperPlugin._command_next)
    assert nxt.parse_args([]).index is None
    assert nxt.parse_args(["3"]).index == 3
    assert nxt.parse_args(["-p"]).portals is True
    walk = _parser(MapperPlugin._command_speedwalk).parse_args(["A", "B"])
    assert (walk.start, walk.target) == ("A", "B")


def test_showroom_shows_details(test_map: Harness) -> None:
    """showroom lists the details of a room, or (none) (#800)."""
    p = test_map.plugin
    p._api_room_add({"uid": "S", "name": "Shop", "details": {"bank": 1, "healer": "Hassan"}})
    text = _text(_run(test_map, "showroom", uid="S"))
    assert "details :" in text
    assert "bank: 1" in text
    assert "healer: Hassan" in text
    assert "details : (none)" in _text(_run(test_map, "showroom", uid="A"))


def test_find_limit_setting(harness: Harness) -> None:
    """find_limit caps the table; 0 shows all; the rows are numbered (#800)."""
    for i in range(FIND_LIMIT + 5):
        harness.plugin._api_room_add({"uid": str(i), "name": "same"})
    harness.settings["find_limit"] = 3
    text = _text(_run(harness, "find", text=["same"]))
    assert "showing 3" in text
    assert text.count("same") == 3
    assert "1 | 0 | same" in text
    assert "3 | 10 | same" in text
    assert harness.plugin.last_find == ["0", "1", "10"]
    harness.settings["find_limit"] = 0
    text = _text(_run(harness, "find", text=["same"]))
    assert text.count("same") == FIND_LIMIT + 5
    assert "showing" not in text
    assert len(harness.plugin.last_find) == FIND_LIMIT + 5
