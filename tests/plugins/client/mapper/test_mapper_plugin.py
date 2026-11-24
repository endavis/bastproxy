"""Tests for the mapper plugin: APIs, change detection and walking."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.plugins.client.mapper.libs._graph import MapGraph
from bastproxy.plugins.client.mapper.libs._schema import DB_NAME, DB_VERSION, TABLES
from bastproxy.plugins.client.mapper.libs._walk import MAX_REROUTES
from bastproxy.plugins.client.mapper.plugin import _mapper as mapper_module
from bastproxy.plugins.client.mapper.plugin._mapper import EVENTS, MapperPlugin

from .conftest import OWNER, FakeApi, Harness, build_map


def test_path_get_shape_and_cost(test_map: Harness) -> None:
    """path.get returns the documented dict."""
    p = test_map.plugin
    path = p._api_path_get("A", "C")
    assert path is not None
    assert set(path) == {"start", "target", "cost", "steps"}
    assert (path["start"], path["target"], path["cost"]) == ("A", "C", 2)
    assert set(path["steps"][0]) == {"fromuid", "touid", "dir", "cost", "requirement"}
    assert p._api_path_get("A", "A") == {"start": "A", "target": "A", "cost": 0, "steps": []}
    assert p._api_path_get("A", "nowhere") is None


def test_requirement_callback(test_map: Harness) -> None:
    """The callback gets the decoded requirement and the exit, once per requirement."""
    p = test_map.plugin
    assert p._api_path_get("A", "E")["cost"] == 4  # no callback: allowed
    calls: list[Any] = []

    def block(requirement: Any, exit_: dict[str, Any]) -> bool:
        calls.append((requirement, exit_["dir"]))
        return False

    p._api_requirement_register("game", block)
    assert p._api_path_get("A", "E")["cost"] == 10
    assert calls == [({"level": 50}, "e")]
    p._api_requirement_register("game", lambda r, e: True)
    assert p._api_path_get("A", "E")["cost"] == 4
    p._api_requirement_unregister("game")
    assert p._active(p.requirement_callbacks) is None


def test_requirement_callback_raising_blocks(test_map: Harness) -> None:
    """A callback that raises counts as blocked."""
    p = test_map.plugin

    def boom(requirement: Any, exit_: dict[str, Any]) -> bool:
        raise RuntimeError("x")

    p._api_requirement_register("game", boom)
    assert p._api_path_get("A", "E")["cost"] == 10


def test_max_depth_setting_and_argument(test_map: Harness) -> None:
    """max_depth defaults to the setting."""
    p = test_map.plugin
    test_map.settings["maxdepth"] = 3
    assert p._api_path_get("A", "E")["cost"] == 10
    assert p._api_path_get("A", "E", 5)["cost"] == 4
    assert p._api_path_get("A", "C", 0) is None


def test_graph_matches_database(test_map: Harness) -> None:
    """After writes, the in-memory graph equals one loaded from the database."""
    p = test_map.plugin
    p._api_exit_remove("A", "s")
    p._api_room_remove("F")
    p._api_exit_add("C", "e", "D", 2)
    fresh = p.store.load_graph()
    assert isinstance(fresh, MapGraph)
    assert fresh.snapshot() == p.graph.snapshot()


def test_room_api(test_map: Harness) -> None:
    """room.get includes exits and note; list, unexplored and remove work."""
    p = test_map.plugin
    assert p._api_room_note_set("A", "hello") is True
    assert p._api_room_note_set("zz", "x") is False
    room = p._api_room_get("A")
    assert room["note"] == "hello"
    assert {e["dir"] for e in room["exits"]} == {"n", "enter portal", "s"}
    assert [r["uid"] for r in p._api_room_list(name="room b")] == ["B"]
    assert [r["uid"] for r in p._api_room_list(flag="noportal")] == ["B"]
    assert [r["uid"] for r in p._api_room_list.__call__(area="test", limit=2)] == ["A", "B"]
    assert [r["uid"] for r in p._api_room_list_unexplored()] == ["E", "F"]
    assert p._api_room_note_get("A") == "hello"
    assert p._api_room_note_remove("A") is True
    assert p._api_room_remove("B") is True
    assert p._api_room_get("B") is None
    assert [e["dir"] for e in p._api_exit_list("A")] == ["enter portal", "s"]
    assert p._api_exit_list("*")[0]["dir"] == "portal f"


def test_area_api(harness: Harness) -> None:
    """Areas add, get, list and remove with their rooms."""
    p = harness.plugin
    assert p._api_area_add("", "x") is False
    assert p._api_area_add("a", "Area A", ["f"], {"k": 1}) is True
    assert p._api_area_get("a")["name"] == "Area A"
    assert [a["uid"] for a in p._api_area_list()] == ["a"]
    p._api_room_add({"uid": "1", "area": "a", "exits": {"n": "2"}})
    p._api_room_add({"uid": "2", "area": "a"})
    p._api_room_add({"uid": "3", "area": "b"})
    p._api_room_note_set("1", "n")
    assert p._api_area_remove("a") == 2
    assert p._api_area_get("a") is None
    assert p._api_room_get("1") is None
    assert p.graph.exits_from("1") == []
    assert p._api_room_get("3") is not None


def test_bad_input_rejected(harness: Harness) -> None:
    """A room without a uid and a bad exit are not stored."""
    p = harness.plugin
    assert p._api_room_add({"name": "x"}) is False
    assert p._api_exit_add("", "n") is False
    assert p._api_exit_add("1", "n", requirement=object()) is False
    assert p._api_exit_add("1", "n", cost=-1) is False
    assert harness.events == []


def test_change_detection(test_map: Harness) -> None:
    """room.add raises room_changed, and room_mismatch only on a contradiction."""
    p = test_map.plugin
    p._api_room_add({"uid": "N", "area": "test"})
    assert test_map.names() == ["room_changed"]
    assert test_map.event("room_changed") == {"uid": "N", "new": True}
    test_map.events.clear()
    p._api_room_add({"uid": "N", "area": "test"})
    assert test_map.names() == ["room_changed"]
    assert test_map.event("room_changed")["new"] is False
    test_map.events.clear()
    p._api_room_add({"uid": "A", "area": "other"})
    assert test_map.event("room_mismatch")["differences"] == {"area": ("test", "other")}
    test_map.events.clear()
    p._api_room_add({"uid": "A", "area": "other", "exits": {"n": "C", "x": "D", "s": "E"}})
    diffs = test_map.event("room_mismatch")["differences"]["exits"]
    assert diffs == {"n": ("B", "C"), "x": (None, "D"), "enter portal": ("C", None)}


def test_unexplored_update_is_not_a_mismatch(test_map: Harness) -> None:
    """An update with -1 keeps the known touid; stored exits missing from it are kept."""
    p = test_map.plugin
    p._api_room_add(
        {"uid": "A", "area": "test", "exits": {"n": "-1", "s": "E", "enter portal": "C"}}
    )
    assert "room_mismatch" not in test_map.names()
    exits = {e["dir"]: e["touid"] for e in p._api_exit_list("A")}
    assert exits == {"n": "B", "s": "E", "enter portal": "C"}


def test_walk_to_target(test_map: Harness) -> None:
    """A walk sends one step, then the next on arrival, then finishes."""
    p = test_map.plugin
    p._api_room_current_set("A")
    test_map.events.clear()
    assert p._api_walk_start("C") is True
    assert test_map.mud == ["n"]
    assert test_map.names() == ["walk_started", "walk_step"]
    p._api_room_current_set("A")  # a re-sent room is ignored
    assert test_map.mud == ["n"]
    p._api_room_current_set("B")
    assert test_map.mud == ["n", "n"]
    assert p._api_walk_get()["state"] == "walking"
    p._api_room_current_set("C")
    assert test_map.mud == ["n", "n"]
    assert test_map.names().count("walk_done") == 1
    assert p._api_walk_get()["state"] == "idle"
    assert test_map.event("walk_done") == {"target": "C"}


def test_walk_never_starts_on_its_own(test_map: Harness) -> None:
    """Arrivals while idle or stopped send nothing and raise no walk events."""
    p = test_map.plugin
    p._api_room_current_set("A")
    p._api_room_current_set("B")
    assert test_map.mud == []
    assert test_map.names() == ["room_arrived", "room_arrived"]
    p._api_walk_start("C")
    p._api_walk_clear()
    test_map.mud.clear()
    test_map.events.clear()
    p._api_room_current_set("C")
    assert test_map.mud == []
    assert not [n for n in test_map.names() if n.startswith("walk")]


def test_walk_start_failures(test_map: Harness) -> None:
    """No current room or no path returns False and raises walk_failed."""
    p = test_map.plugin
    assert p._api_walk_start("C") is False
    assert test_map.event("walk_failed")["reason"] == "current room unknown"
    p._api_room_current_set("A")
    assert p._api_walk_start("nowhere") is False
    assert test_map.event("walk_failed")["reason"] == "no path"
    assert test_map.mud == []


def test_walk_start_at_target(test_map: Harness) -> None:
    """Starting at the target finishes at once."""
    p = test_map.plugin
    p._api_room_current_set("A")
    assert p._api_walk_start("A") is True
    assert test_map.mud == []
    assert test_map.event("walk_done") == {"target": "A"}
    assert p._api_walk_get()["state"] == "idle"


def test_unexpected_room_reroutes(test_map: Harness) -> None:
    """An unexpected room re-paths and continues."""
    p = test_map.plugin
    p._api_room_current_set("A")
    p._api_walk_start("C")
    test_map.mud.clear()
    p._api_room_current_set("D")  # somewhere else
    assert p._api_walk_get()["reroutes"] == 1
    assert test_map.mud == ["recall"]  # D to C goes back through recall
    assert p._api_walk_get()["state"] == "walking"
    assert "walk_failed" not in test_map.names()


def test_unexpected_room_reroute_sends_step(test_map: Harness) -> None:
    """With a path from the new room, the walk goes on from there."""
    p = test_map.plugin
    p._api_room_current_set("A")
    p._api_walk_start("D")
    test_map.mud.clear()
    p._api_room_current_set("C")
    assert test_map.mud == ["e"]
    assert p._api_walk_get()["reroutes"] == 1
    p._api_room_current_set("D")
    assert p._api_walk_get()["state"] == "idle"


def test_reroute_off_and_cap(test_map: Harness) -> None:
    """With reroute off, or after MAX_REROUTES, the walk stops."""
    p = test_map.plugin
    test_map.settings["reroute"] = False
    p._api_room_current_set("A")
    p._api_walk_start("D")
    p._api_room_current_set("C")
    assert p._api_walk_get()["state"] == "stopped"
    test_map.settings["reroute"] = True
    p._api_walk_restart()
    p.walk.reroutes = MAX_REROUTES
    p._api_room_current_set("B")
    assert p._api_walk_get()["state"] == "stopped"
    assert test_map.event("walk_failed")["reason"] == "unexpected room"


def test_restart_and_clear(test_map: Harness) -> None:
    """clear keeps the target, restart re-paths from here; both report state."""
    p = test_map.plugin
    assert p._api_walk_restart() is False
    assert p._api_walk_clear() is False
    p._api_room_current_set("A")
    p._api_walk_start("C")
    assert p._api_walk_clear() is True
    assert test_map.event("walk_failed")["reason"] == "stopped"
    assert p._api_walk_get()["target"] == "C"
    p._api_room_current_set("B")
    test_map.mud.clear()
    assert p._api_walk_restart() is True
    assert test_map.mud == ["n"]
    p._api_room_current_set("C")
    assert p._api_walk_get()["state"] == "idle"


def test_restart_at_target_finishes(test_map: Harness) -> None:
    """Restarting when already at the target finishes at once."""
    p = test_map.plugin
    p._api_room_current_set("A")
    p._api_walk_start("C")
    p._api_walk_clear()
    p.current_room = "C"
    assert p._api_walk_restart() is True
    assert test_map.event("walk_done") == {"target": "C"}


def test_disconnect_stops_walk(test_map: Harness) -> None:
    """The MUD disconnect event stops an active walk."""
    p = test_map.plugin
    p._api_room_current_set("A")
    p._api_walk_start("C")
    p._eventcb_disconnect()
    assert p._api_walk_get()["state"] == "stopped"
    assert test_map.event("walk_failed")["reason"] == "disconnected"


def test_movement_callback(test_map: Harness) -> None:
    """A movement callback is used per step; a bad one falls back to the directions."""
    p = test_map.plugin
    seen: list[list[str]] = []

    def move(steps: list[dict[str, Any]]) -> list[str]:
        seen.append([s["dir"] for s in steps])
        return ["run " + "".join(s["dir"] for s in steps)]

    p._api_movement_register("game", move)
    p._api_room_current_set("A")
    p._api_walk_start("C")
    p._api_room_current_set("B")
    assert seen == [["n"], ["n"]]
    assert test_map.mud == ["run n", "run n"]
    test_map.mud.clear()
    p._api_movement_register("game", lambda steps: 1 / 0)
    assert p._send_steps(p._find("A", "C").steps) == ["n", "n"]
    assert test_map.mud == ["n", "n"]
    p._api_movement_register("game", lambda steps: "no")
    assert p._send_steps(p._find("A", "C").steps) == ["n", "n"]


def test_callbacks_dropped_on_unregister_and_unload(test_map: Harness) -> None:
    """Unregistering or unloading the owner drops its callbacks."""
    p = test_map.plugin
    p._api_movement_register("one", lambda s: ["x"])
    p._api_movement_register("two", lambda s: ["y"])
    assert list(p.movement_callbacks) == ["one", "two"]
    p._api_movement_unregister("two")
    assert list(p.movement_callbacks) == ["one"]
    p._api_requirement_register("one", lambda r, e: True)
    record = {"plugin_id": "one"}
    p.api.table["plugins.core.events:event.current.record.get"] = lambda: record
    p._eventcb_plugin_unloaded()
    assert p.movement_callbacks == {}
    assert p.requirement_callbacks == {}


def test_room_note_shown_on_arrival(test_map: Harness) -> None:
    """A note is shown on arrival when shownotes is on."""
    p = test_map.plugin
    p._api_room_note_set("B", "careful")
    p._api_room_current_set("B")
    assert test_map.client == [["Note: careful"]]
    test_map.settings["shownotes"] = False
    p._api_room_current_set("B")
    assert len(test_map.client) == 1


def test_arrival_event_and_current(test_map: Harness) -> None:
    """room.current.set records the room and raises room_arrived with the previous one."""
    p = test_map.plugin
    p._api_room_current_set("A")
    p._api_room_current_set("B")
    assert test_map.event("room_arrived") == {"uid": "B", "previous": "A"}
    assert p._api_room_current_get() == "B"


def _record(into: list[Any], item: Any, result: Any) -> Any:
    """Record a call and return its result."""
    into.append(item)
    return result


def test_after_load_creates_database(tmp_path: Path) -> None:
    """after_load asks sqldb for the map database with no directory and adds events and settings."""
    p: Any = object.__new__(MapperPlugin)
    p.plugin_id = OWNER
    db = MagicMock()
    db.select.return_value = []
    created: list[Any] = []
    added: list[str] = []
    p.api = FakeApi(
        {
            "plugins.core.sqldb:database.add": lambda *a, **k: _record(created, (a, k), db),
            "plugins.core.events:event.add": lambda name, *a, **k: added.append(name),
            "plugins.core.settings:setting.add": lambda pid, name, *a, **k: added.append(name),
        }
    )
    p._phook_initialize()
    assert created == [((OWNER, DB_NAME, TABLES), {"version": DB_VERSION})]
    assert len(TABLES) == 5
    assert len(added) == len(EVENTS) + 3
    assert {"maxdepth", "shownotes", "reroute"} <= set(added)
    assert p.store.db is db


def test_loading_sends_nothing(test_map: Harness) -> None:
    """Building the map sends nothing to the MUD."""
    assert test_map.mud == []
    assert test_map.plugin.walk.state == "idle"


def test_plugin_is_discovered() -> None:
    """Discovery finds the plugin under the plugins.client package."""
    plugins_dir = Path(__file__).resolve().parents[4] / "src" / "bastproxy" / "plugins"
    result = imputils.find_packages_and_plugins(plugins_dir, "bastproxy.plugins.")
    ids = [item["plugin_id"] for item in result.plugins]
    assert "bastproxy.plugins.client.mapper" in ids
    assert not result.errors


def test_build_map_helper_is_idempotent(harness: Harness) -> None:
    """Building the map twice leaves the same graph."""
    build_map(harness.plugin)
    first = harness.plugin.graph.snapshot()
    build_map(harness.plugin)
    assert harness.plugin.graph.snapshot() == first
    assert mapper_module.EVENT_PREFIX == "ev_plugins.client.mapper_"


@pytest.mark.parametrize("name", list(EVENTS))
def test_events_have_descriptions(name: str) -> None:
    """Every event has a description and argument descriptions."""
    description, args = EVENTS[name]
    assert description
    assert args
