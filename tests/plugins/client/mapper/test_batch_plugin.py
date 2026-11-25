"""Tests for map.batch.add: equivalence with per-item calls, fill mode, one commit."""

import logging
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from bastproxy.plugins.client.mapper.libs._batch import BATCH_LIMIT
from bastproxy.plugins.client.mapper.libs._graph import Exit, MapGraph
from bastproxy.plugins.client.mapper.libs._schema import TABLES
from bastproxy.plugins.client.mapper.libs._store import MapStore
from bastproxy.plugins.core.sqldb.libs._sqlite import create_database

from .conftest import OWNER, Harness, build_map

ROOMS: list[dict[str, Any]] = [
    {"uid": u, "name": f"Room {u}", "area": "test", "flags": ["noportal"] if u == "B" else []}
    for u in "ABCDEF"
]
EXITS: list[dict[str, Any]] = [
    {"fromuid": "A", "dir": "n", "touid": "B"},
    {"fromuid": "B", "dir": "n", "touid": "C"},
    {"fromuid": "A", "dir": "enter portal", "touid": "C", "cost": 5},
    {"fromuid": "C", "dir": "e", "touid": "D"},
    {"fromuid": "D", "dir": "e", "touid": "E", "requirement": {"level": 50}},
    {"fromuid": "A", "dir": "s", "touid": "E", "cost": 10},
    {"fromuid": "*", "dir": "portal f", "touid": "F"},
    {"fromuid": "**", "dir": "recall", "touid": "A"},
    {"fromuid": "E", "dir": "w", "touid": "-1"},
    {"fromuid": "F", "dir": "up", "touid": "-1"},
]


def tables(h: Harness) -> dict[str, list[dict[str, Any]]]:
    """Return every table's rows without the exit_id."""
    db = h.plugin.store.db
    out: dict[str, list[dict[str, Any]]] = {}
    for name, order in (
        ("areas", "uid"),
        ("rooms", "uid"),
        ("exits", "fromuid, dir"),
        ("bookmarks", "uid"),
    ):
        rows = db.select(f"SELECT * FROM {name} ORDER BY {order}")
        out[name] = [{k: v for k, v in r.items() if k != "exit_id"} for r in rows]
    return out


def per_item(h: Harness, rooms: Any, exits: Any, overwrite: bool = True) -> None:
    """Write the same data with the per-item apis, in the batch order."""
    for room in rooms:
        h.plugin._api_room_add(room, accept=True)
    for e in exits:
        h.plugin._api_exit_add(
            e["fromuid"], e["dir"], e.get("touid", "-1"), e.get("cost", 1), e.get("requirement")
        )


def count_releases(h: Harness) -> list[str]:
    """Trace the outermost RELEASE statements of the store connection."""
    seen: list[str] = []
    h.plugin.store.db._conn().set_trace_callback(
        lambda sql: seen.append(sql) if sql.startswith("RELEASE sqldb_0") else None
    )
    return seen


@pytest.fixture
def second(tmp_path: Path, harness: Harness) -> Any:
    """A second harness-like plugin on its own database, sharing the stubs."""
    plugin = object.__new__(type(harness.plugin))
    plugin.__dict__.update(harness.plugin.__dict__)
    db = create_database(OWNER, "map2", TABLES, directory=tmp_path)
    plugin.store = MapStore(db)
    plugin.graph = MapGraph()
    other = Harness(plugin)
    other.events = harness.events
    yield other
    db.close()


def test_batch_equals_per_item(harness: Harness, second: Harness) -> None:
    build_map(harness.plugin)
    result = second.plugin._api_map_batch_add(rooms=ROOMS, exits=EXITS)
    assert result == {
        "areas": 0,
        "rooms": 6,
        "new_rooms": 6,
        "exits": 10,
        "new_exits": 10,
        "notes": 0,
        "skipped": 0,
    }
    assert tables(second) == tables(harness)
    assert second.plugin.graph.snapshot() == harness.plugin.graph.snapshot()
    assert second.plugin.graph.snapshot() == second.plugin.store.load_graph().snapshot()


def test_batch_equals_per_item_on_conflicting_data(harness: Harness, second: Harness) -> None:
    for h in (harness, second):
        build_map(h.plugin)
    rooms = [
        {
            "uid": "A",
            "name": "New A",
            "area": "other",
            "flags": ["x"],
            "exits": {"n": "C", "w": "Z"},
        },
        {"uid": "A", "name": "Again", "flags": ["y"]},
        {"uid": "G", "name": "G", "exits": {"up": "A"}},
    ]
    exits = [
        {"fromuid": "E", "dir": "w", "touid": "A", "cost": 3},
        {"fromuid": "E", "dir": "w", "touid": "-1", "cost": 4},
        {"fromuid": "A", "dir": "s", "touid": "-1", "cost": 2, "requirement": {"k": 1}},
    ]
    per_item(harness, rooms, exits)
    second.plugin._api_map_batch_add(rooms=rooms, exits=exits)
    assert tables(second) == tables(harness)
    assert second.plugin.graph.snapshot() == harness.plugin.graph.snapshot()
    assert second.plugin.graph.snapshot() == second.plugin.store.load_graph().snapshot()


def test_duplicates_in_one_batch(harness: Harness, second: Harness) -> None:
    rooms = [{"uid": "1", "name": "a"}, {"uid": "1", "name": "b", "flags": ["f"]}]
    exits = [
        {"fromuid": "1", "dir": "n", "touid": "2"},
        {"fromuid": "1", "dir": "n", "touid": "-1", "cost": 3},
    ]
    per_item(harness, rooms, exits)
    second.plugin._api_map_batch_add(rooms=rooms, exits=exits)
    assert tables(second) == tables(harness)
    assert second.plugin.graph.snapshot() == harness.plugin.graph.snapshot()


def test_unknown_touid_keeps_known(test_map: Harness) -> None:
    test_map.plugin._api_map_batch_add(exits=[{"fromuid": "A", "dir": "n", "touid": "-1"}])
    assert test_map.plugin.store.get_exit("A", "n").touid == "B"
    assert {e.dir: e.touid for e in test_map.plugin.graph.exits_from("A")}["n"] == "B"


def test_fill_mode(test_map: Harness) -> None:
    p = test_map.plugin
    p._api_area_add("test", "Test Area")
    p._api_room_note_set("A", "kept note")
    before = tables(test_map)
    result = p._api_map_batch_add(
        areas=[{"uid": "test", "name": "Replaced"}, {"uid": "new", "name": "New"}],
        rooms=[
            {"uid": "A", "name": "Other", "area": "elsewhere", "flags": ["shop"]},
            {"uid": "NEW", "name": "Fresh"},
        ],
        exits=[
            {"fromuid": "E", "dir": "w", "touid": "A", "cost": 9},
            {"fromuid": "A", "dir": "n", "touid": "Z", "cost": 9},
            {"fromuid": "A", "dir": "s", "touid": "Z", "requirement": {"r": 1}},
            {"fromuid": "D", "dir": "e", "touid": "Z", "requirement": {"r": 1}},
        ],
        notes={"A": "ignored", "B": "filled", "NEW": "fresh note"},
        overwrite=False,
    )
    assert result == {
        "areas": 1,
        "rooms": 2,
        "new_rooms": 1,
        "exits": 2,
        "new_exits": 0,
        "notes": 2,
        "skipped": 0,
    }
    assert p.store.get_area("test")["name"] == "Test Area"
    room = p.store.get_room("A")
    assert room["name"] == "Room A"
    assert room["area"] == "test"
    assert room["flags"] == ["shop"]
    assert p.store.get_exit("E", "w").touid == "A"
    assert p.store.get_exit("E", "w").cost == 1
    assert p.store.get_exit("A", "n").touid == "B"
    assert p.store.get_exit("A", "s").requirement == {"r": 1}
    assert p.store.get_exit("A", "s").cost == 10
    assert p.store.get_exit("D", "e").requirement == {"level": 50}
    assert p.store.get_note("A") == "kept note"
    assert p.store.get_note("B") == "filled"
    after = tables(test_map)
    assert after["exits"] != before["exits"]
    assert p.graph.snapshot() == p.store.load_graph().snapshot()


def test_fill_mode_over_identical_data_raises_nothing(test_map: Harness) -> None:
    p = test_map.plugin
    p._api_map_batch_add(rooms=ROOMS, exits=EXITS, overwrite=False)
    assert test_map.events == []


def test_notes_need_a_room(test_map: Harness) -> None:
    p = test_map.plugin
    result = p._api_map_batch_add(rooms=[{"uid": "N"}], notes={"N": "in batch", "Q": "no room"})
    assert result["notes"] == 1
    assert result["skipped"] == 1
    assert p.store.get_note("N") == "in batch"
    assert p.store.get_note("Q") is None


def test_bad_items_are_skipped(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    p = harness.plugin
    with caplog.at_level(logging.WARNING):
        result = p._api_map_batch_add(
            areas=[{"uid": ""}],
            rooms=[{"name": "no uid"}, {"uid": "1"}],
            exits=[
                {"fromuid": "1", "dir": "n", "cost": -1},
                {"fromuid": "1", "dir": "s", "requirement": object()},
                {"fromuid": "", "dir": "e"},
                {"fromuid": "1", "dir": "w", "touid": "2"},
            ],
        )
    assert result == {
        "areas": 0,
        "rooms": 1,
        "new_rooms": 1,
        "exits": 1,
        "new_exits": 1,
        "notes": 0,
        "skipped": 5,
    }
    assert [e.dir for e in p.store.exits_from("1")] == ["w"]
    assert sum("skipped 5" in r.getMessage() for r in caplog.records) == 1


def test_over_the_limit_writes_nothing(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    p = harness.plugin
    rooms = [{"uid": str(i), "exits": {"n": "x"}} for i in range(BATCH_LIMIT // 2)]
    rooms.append({"uid": "last"})
    with caplog.at_level(logging.WARNING):
        assert p._api_map_batch_add(rooms=rooms) is None
    assert p.store.list_rooms() == []
    assert harness.events == []
    assert any("over the limit" in r.getMessage() for r in caplog.records)
    assert p._api_map_batch_add(rooms=rooms[:-1]) is not None


def test_one_commit_per_call(harness: Harness) -> None:
    releases = count_releases(harness)
    harness.plugin._api_map_batch_add(
        areas=[{"uid": "a"}], rooms=ROOMS, exits=EXITS, notes={"A": "x"}
    )
    assert len(releases) == 1


def test_one_summary_event(harness: Harness) -> None:
    harness.plugin._api_map_batch_add(rooms=ROOMS, exits=EXITS)
    assert harness.names() == ["map_changed"]
    assert harness.event("map_changed")["rooms"] == 6


def test_copy_on_write_keeps_frozen_views(test_map: Harness) -> None:
    p = test_map.plugin
    view = p.graph.freeze()
    before = view.snapshot()
    p._api_map_batch_add(
        rooms=[{"uid": "Z", "exits": {"n": "A"}}],
        exits=[{"fromuid": "A", "dir": "x", "touid": "Z"}],
    )
    assert view.snapshot() == before
    assert "Z" in p.graph.snapshot()["rooms"]


def test_failure_writes_nothing_and_leaves_graph(harness: Harness) -> None:
    p = harness.plugin
    build_map(p)
    harness.events.clear()
    graph_before = p.graph.snapshot()
    tables_before = tables(harness)
    real = p.store.db.modifymany

    def failing(sql: str, data: Any = None) -> Any:
        if "INTO exits" in sql:
            raise sqlite3.OperationalError("boom")
        return real(sql, data)

    with (
        patch.object(p.store.db, "modifymany", side_effect=failing),
        pytest.raises(sqlite3.Error),
    ):
        p._api_map_batch_add(
            rooms=[{"uid": "Q", "name": "q"}],
            exits=[{"fromuid": "Q", "dir": "n", "touid": "A"}],
            notes={"A": "n"},
        )
    assert tables(harness) == tables_before
    assert p.graph.snapshot() == graph_before
    assert harness.events == []


def test_embedded_exits_keep_lock_explicit_overwrite(test_map: Harness) -> None:
    """In overwrite mode an embedded exit keeps the lock, an explicit one replaces it (#762)."""
    p = test_map.plugin
    p._api_exit_add("A", "n", "B", 3, {"level": 100})
    p._api_map_batch_add(rooms=[{"uid": "A", "area": "test", "exits": {"n": "B"}}])
    assert p.store.get_exit("A", "n") == Exit("A", "n", "B", 3, {"level": 100})
    assert {e.dir: e for e in p.graph.exits_from("A")}["n"].cost == 3
    p._api_map_batch_add(exits=[{"fromuid": "A", "dir": "n", "touid": "B"}])
    assert p.store.get_exit("A", "n") == Exit("A", "n", "B", 1, None)


def test_batch_equals_per_item_with_locks(harness: Harness, second: Harness) -> None:
    """Embedded and explicit exits of one batch end as the per-item calls would (#762)."""
    for h in (harness, second):
        build_map(h.plugin)
        h.plugin._api_exit_add("A", "n", "B", 3, {"level": 100})
        h.plugin._api_exit_add("B", "n", "C", 4, {"level": 5})
    rooms = [
        {"uid": "A", "area": "test", "exits": {"n": "C", "e": "-1"}},
        {"uid": "B", "area": "test", "exits": {"n": "C"}},
    ]
    exits = [
        {"fromuid": "B", "dir": "n", "touid": "C", "cost": 2},
        {"fromuid": "A", "dir": "e", "touid": "D", "cost": 7, "requirement": {"k": 1}},
    ]
    per_item(harness, rooms, exits)
    second.plugin._api_map_batch_add(rooms=rooms, exits=exits)
    assert tables(second) == tables(harness)
    assert second.plugin.graph.snapshot() == harness.plugin.graph.snapshot()
    assert second.plugin.store.get_exit("A", "n") == Exit("A", "n", "C", 3, {"level": 100})


def test_new_exits_overwrite_mode_counts_only_unstored_keys(test_map: Harness) -> None:
    result = test_map.plugin._api_map_batch_add(
        exits=[
            {"fromuid": "A", "dir": "n", "touid": "C", "cost": 4},
            {"fromuid": "A", "dir": "up", "touid": "B"},
            {"fromuid": "*", "dir": "portal f", "touid": "E"},
            {"fromuid": "*", "dir": "portal g", "touid": "E"},
            {"fromuid": "**", "dir": "recall", "touid": "B"},
            {"fromuid": "**", "dir": "recall home", "touid": "A"},
        ]
    )
    assert result["exits"] == 6
    assert result["new_exits"] == 3
    assert result["exits"] - result["new_exits"] == 3


def test_new_exits_fill_mode_counts_only_unstored_keys(test_map: Harness) -> None:
    result = test_map.plugin._api_map_batch_add(
        exits=[
            {"fromuid": "A", "dir": "s", "touid": "Z", "requirement": {"r": 1}},
            {"fromuid": "A", "dir": "up", "touid": "B"},
            {"fromuid": "*", "dir": "portal g", "touid": "E"},
            {"fromuid": "**", "dir": "recall", "touid": "B"},
        ],
        overwrite=False,
    )
    assert result["exits"] == 3
    assert result["new_exits"] == 2


def test_new_exits_embedded_and_explicit(test_map: Harness) -> None:
    result = test_map.plugin._api_map_batch_add(
        rooms=[{"uid": "A", "exits": {"n": "B", "w": "F"}}, {"uid": "NEW", "exits": {"s": "A"}}],
        exits=[
            {"fromuid": "B", "dir": "s", "touid": "A"},
            {"fromuid": "B", "dir": "n", "touid": "D"},
        ],
    )
    assert result["exits"] == 4
    assert result["new_exits"] == 3


def test_new_exits_repeated_key_counts_once(harness: Harness) -> None:
    result = harness.plugin._api_map_batch_add(
        rooms=[{"uid": "A", "exits": {"n": "B"}}],
        exits=[
            {"fromuid": "A", "dir": "n", "touid": "C"},
            {"fromuid": "A", "dir": "n", "touid": "D"},
            {"fromuid": "*", "dir": "p", "touid": "A"},
            {"fromuid": "*", "dir": "p", "touid": "B"},
        ],
    )
    assert result["exits"] == 2
    assert result["new_exits"] == 2
    again = harness.plugin._api_map_batch_add(exits=[{"fromuid": "*", "dir": "p", "touid": "C"}])
    assert again["new_exits"] == 0
    assert again["exits"] == 1


def test_map_changed_event_carries_new_exits(harness: Harness) -> None:
    harness.plugin._api_map_batch_add(rooms=ROOMS, exits=EXITS)
    assert harness.event("map_changed")["new_exits"] == 10
    harness.events.clear()
    harness.plugin._api_map_batch_add(exits=[{"fromuid": "A", "dir": "n", "touid": "C"}])
    assert harness.event("map_changed")["new_exits"] == 0
