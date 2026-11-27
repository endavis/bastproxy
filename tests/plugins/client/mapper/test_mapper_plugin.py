"""Tests for the mapper plugin: APIs, change detection and walking."""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from bastproxy.libs.plugins import imputils
from bastproxy.plugins.client.mapper.libs._graph import Exit, MapGraph
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
    assert diffs == {"n": ("B", "C"), "x": (None, "D")}


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


def test_path_get_portals_and_recalls(test_map: Harness) -> None:
    """path.get can leave out the exits from ``*`` and ``**`` (#798)."""
    p = test_map.plugin
    assert p._api_path_get("A", "F", portals=False) is None
    default = p._api_path_get("A", "F")
    assert default is not None
    assert [s["dir"] for s in default["steps"]] == ["portal f"]
    assert p._api_path_get("E", "A", recalls=False) is None
    assert p._api_path_get("E", "A", portals=False) is not None


def test_walk_start_without_portals_or_recalls(test_map: Harness) -> None:
    """walk.start with the options off fails where only a portal or recall leads (#798)."""
    p = test_map.plugin
    p._api_room_current_set("A")
    assert p._api_walk_start("F", portals=False) is True
    assert test_map.event("walk_failed")["reason"] == "no path"
    assert test_map.mud == []
    p._api_room_current_set("E")
    assert p._api_walk_start("A", recalls=False) is True
    assert test_map.event("walk_failed")["reason"] == "no path"
    assert test_map.mud == []
    assert p._api_walk_start("A") is True
    assert test_map.mud == ["recall"]


def test_walk_start_failures(test_map: Harness) -> None:
    """No current room or no path returns False and raises walk_failed."""
    p = test_map.plugin
    assert p._api_walk_start("C") is False
    assert test_map.event("walk_failed")["reason"] == "current room unknown"
    p._api_room_current_set("A")
    assert p._api_walk_start("nowhere") is True
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
    assert len(added) == len(EVENTS) + 4
    assert {"maxdepth", "shownotes", "reroute", "find_limit"} <= set(added)
    assert p.store.db is db


def test_find_limit_setting_is_added() -> None:
    """after_load adds find_limit, default 50, 0 allowed, negatives and bools refused (#800)."""
    p: Any = object.__new__(MapperPlugin)
    p.plugin_id = OWNER
    db = MagicMock()
    db.select.return_value = []
    kwargs: dict[str, dict[str, Any]] = {}
    defaults: dict[str, Any] = {}

    def add_setting(_pid: str, name: str, default: Any, *_a: Any, **k: Any) -> None:
        kwargs[name] = k
        defaults[name] = default

    p.api = FakeApi(
        {
            "plugins.core.sqldb:database.add": lambda *a, **k: db,
            "plugins.core.events:event.add": lambda *a, **k: None,
            "plugins.core.settings:setting.add": add_setting,
        }
    )
    p._phook_initialize()
    assert defaults["find_limit"] == 50
    validator = kwargs["find_limit"]["validator"]
    assert validator(0) == ""
    assert validator(-1) != ""
    assert validator(True) != ""


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


# searches in a worker thread
def _blocking_find(gate: threading.Event, seen: list[int]) -> Any:
    """Wrap find_path so it waits for ``gate`` in the worker thread."""
    real = mapper_module.find_path

    def blocked(*args: Any, **kwargs: Any) -> Any:
        seen.append(threading.get_ident())
        assert gate.wait(5)
        return real(*args, **kwargs)

    return blocked


async def _finish(h: Harness) -> None:
    await asyncio.wait_for(asyncio.gather(*h.tasks), 10)


async def test_search_does_not_block_loop(
    test_map: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop keeps running while a walk search waits in its worker."""
    p = test_map.plugin
    p._api_room_current_set("A")
    gate = threading.Event()
    seen: list[int] = []
    monkeypatch.setattr(mapper_module, "find_path", _blocking_find(gate, seen))
    assert p._api_walk_start("C") is True
    assert p._api_walk_get()["state"] == "searching"
    ran: list[bool] = []

    async def other() -> None:
        ran.append(True)
        gate.set()

    await asyncio.wait_for(other(), 5)
    await _finish(test_map)
    assert ran == [True]
    assert seen
    assert seen[0] != threading.get_ident()
    assert "walk_started" in test_map.names()
    assert test_map.mud == ["n"]


async def test_graph_changes_during_search(
    test_map: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writes while the search waits do not change its result or the database match."""
    p = test_map.plugin
    p._api_room_current_set("A")
    gate = threading.Event()
    monkeypatch.setattr(mapper_module, "find_path", _blocking_find(gate, []))
    p._api_walk_start("C")
    p._api_exit_remove("A", "n")
    p._api_room_remove("B")
    p._api_exit_add("A", "x", "F")
    gate.set()
    await _finish(test_map)
    steps = test_map.event("walk_started")["steps"]
    assert [s["dir"] for s in steps] == ["n", "n"]
    assert p.graph.snapshot() == p.store.load_graph().snapshot()


async def test_requirement_callback_on_loop(
    test_map: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The callback runs on the loop thread once per requirement in the map."""
    p = test_map.plugin
    p._api_exit_add("A", "up", "F", 1, {"level": 99})
    threads: list[int] = []
    asked: list[Any] = []

    def callback(requirement: Any, _exit: dict[str, Any]) -> bool:
        threads.append(threading.get_ident())
        asked.append(requirement)
        return False

    p._api_requirement_register("t", callback)
    p._api_room_current_set("A")
    p._api_walk_start("C")
    await _finish(test_map)
    assert set(threads) == {threading.get_ident()}
    assert sorted(asked, key=str) == [{"level": 50}, {"level": 99}]


async def test_raising_callback_blocks_in_thread_search(test_map: Harness) -> None:
    """A callback that raises blocks the exit for a threaded search."""
    p = test_map.plugin

    def broken(_r: Any, _e: dict[str, Any]) -> bool:
        raise RuntimeError("boom")

    p._api_requirement_register("t", broken)
    p._api_room_current_set("D")
    p._api_walk_start("E")
    await _finish(test_map)
    steps = test_map.event("walk_started")["steps"]
    assert [s["dir"] for s in steps] == ["recall", "s"]


async def test_clear_during_search_drops_result(
    test_map: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """walk.clear stops the search; restart gives one walk_started."""
    p = test_map.plugin
    p._api_room_current_set("A")
    gate = threading.Event()
    monkeypatch.setattr(mapper_module, "find_path", _blocking_find(gate, []))
    p._api_walk_start("C")
    assert p._api_walk_clear("stopped") is True
    assert p._api_walk_get()["state"] == "stopped"
    gate.set()
    await _finish(test_map)
    assert "walk_started" not in test_map.names()
    p._api_walk_start("C")
    await _finish(test_map)
    assert test_map.names().count("walk_started") == 1


async def test_superseded_start_gives_one_walk_started(
    test_map: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """clear then restart before the first search ends leaves a single walk_started."""
    p = test_map.plugin
    p._api_room_current_set("A")
    gate = threading.Event()
    monkeypatch.setattr(mapper_module, "find_path", _blocking_find(gate, []))
    p._api_walk_start("C")
    p._api_walk_clear("stopped")
    assert p._api_walk_restart() is True
    gate.set()
    await _finish(test_map)
    assert test_map.names().count("walk_started") == 1


async def test_moved_during_search(test_map: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """A move while searching fails the walk, which can be resumed."""
    p = test_map.plugin
    p._api_room_current_set("A")
    gate = threading.Event()
    monkeypatch.setattr(mapper_module, "find_path", _blocking_find(gate, []))
    p._api_walk_start("C")
    p._api_room_current_set("B")
    gate.set()
    await _finish(test_map)
    assert test_map.event("walk_failed")["reason"] == "moved during search"
    assert p._api_walk_get()["state"] == "stopped"
    monkeypatch.undo()
    assert p._api_walk_restart() is True
    await _finish(test_map)
    assert p._api_walk_get()["state"] == "walking"


async def test_reroute_while_searching(test_map: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second arrival during a reroute search is ignored."""
    p = test_map.plugin
    p._api_room_current_set("A")
    p._api_walk_start("C")
    await _finish(test_map)
    test_map.tasks.clear()
    gate = threading.Event()
    monkeypatch.setattr(mapper_module, "find_path", _blocking_find(gate, []))
    p._api_room_current_set("D")
    assert p._api_walk_get()["state"] == "searching"
    p._api_room_current_set("D")
    gate.set()
    await _finish(test_map)
    assert p.walk.reroutes == 1
    assert p._api_walk_get()["state"] == "walking"


async def test_search_error_fails_walk(test_map: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker that raises is logged and fails the walk instead of hanging."""
    p = test_map.plugin
    p._api_room_current_set("A")

    def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(mapper_module, "find_path", boom)
    p._api_walk_start("C")
    await _finish(test_map)
    assert test_map.event("walk_failed")["reason"] == "search failed"
    assert p._api_walk_get()["state"] == "stopped"


async def test_unload_during_search(test_map: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """A search that ends after unload does nothing."""
    p = test_map.plugin
    p._api_room_current_set("A")
    gate = threading.Event()
    monkeypatch.setattr(mapper_module, "find_path", _blocking_find(gate, []))
    p._api_walk_start("C")
    p._phook_mapper_uninitialize()
    gate.set()
    await _finish(test_map)
    assert "walk_started" not in test_map.names()


def test_room_add_keeps_exit_lock(test_map: Harness) -> None:
    """Recapturing a room keeps an exit's cost and requirement, in the db and graph (#762)."""
    p = test_map.plugin
    p._api_exit_add("A", "n", "B", 3, {"level": 100})
    p._api_room_add({"uid": "A", "name": "Room A", "area": "test", "exits": {"n": "B", "w": "-1"}})
    assert p.store.get_exit("A", "n") == Exit("A", "n", "B", 3, {"level": 100})
    graph_exit = {e.dir: e for e in p.graph.exits_from("A")}["n"]
    assert (graph_exit.cost, graph_exit.requirement) == (3, {"level": 100})
    # a new exit from room.add gets the defaults
    assert p.store.get_exit("A", "w") == Exit("A", "w", "-1", 1, None)


def test_room_add_recapture_still_blocks_locked_exit(test_map: Harness) -> None:
    """A requirement callback still rejects a locked exit after the room is recaptured."""
    p = test_map.plugin
    p._api_requirement_register("game", lambda r, e: r != {"level": 100})
    p._api_exit_add("A", "n", "B", 1, {"level": 100})
    p._api_room_add({"uid": "A", "area": "test", "exits": {"n": "B"}})
    assert p._api_path_get("A", "B") is None  # the only way to B is the locked exit


def test_exit_add_still_overwrites_lock(test_map: Harness) -> None:
    """An explicit exit.add sets cost and requirement."""
    p = test_map.plugin
    p._api_exit_add("A", "n", "B", 3, {"level": 100})
    p._api_exit_add("A", "n", "B", 2, None)
    assert p.store.get_exit("A", "n") == Exit("A", "n", "B", 2, None)
    assert {e.dir: e for e in p.graph.exits_from("A")}["n"].cost == 2


# ---- mismatch handling (#795, #796, #797) ----


def _mismatch_on_a(h: Harness) -> None:
    """Lock A n -> B, then send an update that contradicts area and exits."""
    p = h.plugin
    p._api_exit_add("A", "n", "B", 3, {"level": 100})
    h.events.clear()
    p._api_room_add({"uid": "A", "name": "New A", "area": "other", "exits": {"n": "C", "w": "Z"}})


def test_hybrid_policy_holds_area_and_exits(test_map: Harness) -> None:
    """Name updates, the area and the touid of an existing exit are held (#796)."""
    p = test_map.plugin
    _mismatch_on_a(test_map)
    diffs = test_map.event("room_mismatch")["differences"]
    assert diffs["area"] == ("test", "other")
    assert diffs["name"] == ("Room A", "New A")
    assert diffs["exits"] == {"n": ("B", "C"), "w": (None, "Z"), "s": ("E", None)}
    room = p.store.get_room("A")
    assert room is not None
    assert (room["area"], room["name"]) == ("test", "New A")
    kept = p.store.get_exit("A", "n")
    assert kept is not None
    assert (kept.touid, kept.cost, kept.requirement) == ("B", 3, {"level": 100})
    assert p.graph.snapshot() == p.store.load_graph().snapshot()
    assert p.store.get_exit("A", "w") is not None
    assert p.store.get_exit("A", "s") is not None
    assert "A" in p.mismatches


def test_partial_update_keeps_area(test_map: Harness) -> None:
    """An update without an area keeps the stored one and raises no mismatch."""
    p = test_map.plugin
    p._api_room_add({"uid": "A", "name": "Room A"})
    room = p.store.get_room("A")
    assert room is not None
    assert room["area"] == "test"
    assert "room_mismatch" not in test_map.names()


def test_empty_stored_area_is_filled(harness: Harness) -> None:
    """A room stored without an area gets one from a later update."""
    p = harness.plugin
    p._api_room_add({"uid": "1", "name": "x"})
    harness.events.clear()
    p._api_room_add({"uid": "1", "name": "x", "area": "a"})
    room = p.store.get_room("1")
    assert room is not None
    assert room["area"] == "a"
    assert "room_mismatch" not in harness.names()


def test_room_add_accept(test_map: Harness) -> None:
    """accept=True replaces the area and touids, keeps the lock, raises no mismatch."""
    p = test_map.plugin
    _mismatch_on_a(test_map)
    test_map.events.clear()
    p._api_room_add({"uid": "A", "area": "other", "exits": {"n": "C", "w": "Z"}}, accept=True)
    room = p.store.get_room("A")
    assert room is not None
    assert room["area"] == "other"
    moved = p.store.get_exit("A", "n")
    assert moved is not None
    assert (moved.touid, moved.cost, moved.requirement) == ("C", 3, {"level": 100})
    assert "room_mismatch" not in test_map.names()
    assert "A" not in p.mismatches


def test_pending_cleanup(test_map: Harness) -> None:
    """A matching update, room.remove and area.remove drop the held update."""
    p = test_map.plugin
    _mismatch_on_a(test_map)
    p._api_room_add({"uid": "A", "area": "test"})
    assert "A" not in p.mismatches
    _mismatch_on_a(test_map)
    p._api_room_remove("A")
    assert "A" not in p.mismatches
    p._api_room_add({"uid": "B", "area": "other"})
    assert "B" in p.mismatches
    p._api_area_remove("test")
    assert p.mismatches == {}


def test_ignoreexits_room(test_map: Harness) -> None:
    """A flagged room writes contradicting touids, but still holds an area change."""
    p = test_map.plugin
    assert p._api_room_flag_add("A", "ignoreexits") is True
    p._api_room_add({"uid": "A", "area": "other", "exits": {"n": "C"}})
    diffs = test_map.event("room_mismatch")["differences"]
    assert diffs == {"area": ("test", "other")}
    exit_n = p.store.get_exit("A", "n")
    assert exit_n is not None
    assert exit_n.touid == "C"
    room = p.store.get_room("A")
    assert room is not None
    assert room["area"] == "test"


def test_room_add_keeps_ignoreexits_flag(test_map: Harness) -> None:
    """An update whose flags leave ignoreexits out keeps it; no flags key keeps all."""
    p = test_map.plugin
    p._api_room_flag_add("A", "ignoreexits")
    p._api_room_add({"uid": "A", "area": "test", "flags": ["shop"]})
    room = p.store.get_room("A")
    assert room is not None
    assert room["flags"] == ["shop", "ignoreexits"]
    p._api_room_add({"uid": "A", "area": "test"})
    room = p.store.get_room("A")
    assert room is not None
    assert room["flags"] == ["shop", "ignoreexits"]
    assert p.graph.room_flags("A") == frozenset({"shop", "ignoreexits"})


def test_room_flag_api(test_map: Harness) -> None:
    """room.flag.add and room.flag.remove return, store and update the graph."""
    p = test_map.plugin
    assert p._api_room_flag_add("zz", "x") is False
    assert p._api_room_flag_add("A", "x") is True
    assert p._api_room_flag_add("A", "x") is True
    room = p.store.get_room("A")
    assert room is not None
    assert room["flags"] == ["x"]
    assert p.graph.room_flags("A") == frozenset({"x"})
    assert p._api_room_flag_remove("A", "y") is False
    assert p._api_room_flag_remove("zz", "x") is False
    assert p._api_room_flag_remove("A", "x") is True
    room = p.store.get_room("A")
    assert room is not None
    assert room["flags"] == []
    assert p.graph.room_flags("A") == frozenset()


def test_mapper_accepts_command_extensions(harness: Harness) -> None:
    """Game adapters add commands under the mapper (#834, ADR-0024)."""
    plugin: Any = object.__new__(type(harness.plugin))
    plugin.plugin_id = harness.plugin.plugin_id
    plugin.api = harness.plugin.api
    type(plugin)._phook_init_plugin(plugin)
    assert plugin.accepts_command_extensions_f is True


def test_marker_callback_gets_a_copy_and_its_list(test_map: Harness) -> None:
    """The callback sees a copy of the room dict and its list of str is the room's markers."""
    p = test_map.plugin
    room = {"uid": "A", "name": "Room A"}

    def mark(given: dict[str, Any]) -> list[str]:
        given["name"] = "changed"
        return ["x", "y"]

    assert p._room_markers(room) == []  # no callback
    p._api_room_marker_register("game", mark)
    assert p._room_markers(room) == ["x", "y"]
    assert room["name"] == "Room A"


def test_marker_callback_that_raises_or_returns_bad_data_gives_no_markers(
    test_map: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    p = test_map.plugin
    room = {"uid": "A"}
    for bad in (lambda r: 1 / 0, lambda r: "no", lambda r: ["a", 1], lambda r: None):
        p._api_room_marker_register("game", bad)
        caplog.clear()
        with caplog.at_level(logging.ERROR):
            assert p._room_markers(room) == []
        assert any("marker callback failed" in r.getMessage() for r in caplog.records)


def test_terrain_colors_validation_and_replacement(
    test_map: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    p = test_map.plugin
    with caplog.at_level(logging.WARNING):
        p._api_terrain_color_register(
            "game", {"a": "#fff", "b": "red", "c": "#12345g", "d": "#abcdef"}
        )
    assert p.terrain_color_maps == {"game": {"a": "#fff", "d": "#abcdef"}}
    assert sum("invalid colours dropped" in r.getMessage() for r in caplog.records) == 1
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        p._api_terrain_color_register("game", {"a": "#000"})
        assert caplog.records == []  # the same owner replacing itself is silent
        p._api_terrain_color_register("other", {"a": "#111"})
    assert any("replaces the one of game" in r.getMessage() for r in caplog.records)
    assert p._active(p.terrain_color_maps) == {"a": "#111"}
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        p._api_terrain_color_register("bad", ["#fff"])
    assert "bad" not in p.terrain_color_maps
    assert any("not a mapping" in r.getMessage() for r in caplog.records)


def test_marker_and_color_callbacks_dropped_on_unregister_and_unload(test_map: Harness) -> None:
    p = test_map.plugin
    p._api_room_marker_register("one", lambda r: ["x"])
    p._api_room_marker_register("two", lambda r: ["y"])
    p._api_terrain_color_register("one", {"a": "#fff"})
    p._api_terrain_color_register("two", {"a": "#000"})
    p._api_room_marker_unregister("two")
    p._api_terrain_color_unregister("two")
    assert list(p.marker_callbacks) == ["one"]
    assert list(p.terrain_color_maps) == ["one"]
    record = {"plugin_id": "one"}
    p.api.table["plugins.core.events:event.current.record.get"] = lambda: record
    p._eventcb_plugin_unloaded()
    assert p.marker_callbacks == {}
    assert p.terrain_color_maps == {}
