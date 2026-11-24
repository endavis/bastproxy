"""Tests for the map store, on a real database."""

import json
from pathlib import Path

import pytest

from bastproxy.plugins.client.mapper.libs._graph import Exit
from bastproxy.plugins.client.mapper.libs._schema import TABLES
from bastproxy.plugins.client.mapper.libs._store import MapStore, room_differences
from bastproxy.plugins.core.sqldb.libs._sqlite import create_database


@pytest.fixture
def store(tmp_path: Path) -> MapStore:
    """A store on a fresh database."""
    return MapStore(create_database("plugins.client.mapper", "map", TABLES, directory=tmp_path))


def test_tables_created(store: MapStore) -> None:
    """The five tables exist."""
    rows = store.db.select("SELECT name FROM sqlite_master WHERE type = 'table'")
    names = {r["name"] for r in rows}
    assert {t["name"] for t in TABLES} <= names


def test_room_roundtrip_and_list(store: MapStore) -> None:
    """Rooms store, read back and list by name, area and flag."""
    store.upsert_room({"uid": "1", "name": "Main Hall", "area": "a", "flags": ["shop"]})
    store.upsert_room({"uid": "2", "name": "Cellar", "area": "b", "details": {"k": 1}})
    room = store.get_room("1")
    assert room is not None
    assert room["flags"] == ["shop"]
    assert room["details"] == {}
    assert [r["uid"] for r in store.list_rooms(name="hall")] == ["1"]
    assert [r["uid"] for r in store.list_rooms(area="b")] == ["2"]
    assert [r["uid"] for r in store.list_rooms(flag="shop")] == ["1"]
    assert len(store.list_rooms(limit=1)) == 1
    assert store.get_room("zz") is None


def test_values_are_bound_safely(store: MapStore) -> None:
    """Quotes and LIKE wildcards in a name store and search literally."""
    store.upsert_room({"uid": "1", "name": "Bob's 100% room_x"})
    store.upsert_room({"uid": "2", "name": "Bob's 1000 roomyx"})
    assert [r["uid"] for r in store.list_rooms(name="100% room_x")] == ["1"]
    assert [r["uid"] for r in store.list_rooms(name="'s 10")] == ["1", "2"]


def test_exits_roundtrip(store: MapStore) -> None:
    """Requirements round-trip through JSON and unexplored never overwrites known."""
    for requirement in (50, {"level": 5}, None):
        stored = store.upsert_exit(Exit("1", "n", "2", 3, requirement))
        assert stored.requirement == requirement
    store.upsert_exit(Exit("1", "n", "-1"))
    exit_ = store.get_exit("1", "n")
    assert exit_ is not None
    assert exit_.touid == "2"
    store.upsert_exit(Exit("*", "portal", "5"))
    assert [e.dir for e in store.exits_from("*")] == ["portal"]
    assert store.remove_exit("1", "n") is True
    assert store.remove_exit("1", "n") is False


def test_remove_room_cascades(store: MapStore) -> None:
    """Removing a room removes exits from and to it and its note."""
    for uid in ("1", "2"):
        store.upsert_room({"uid": uid})
    store.upsert_exit(Exit("1", "n", "2"))
    store.upsert_exit(Exit("2", "s", "1"))
    store.set_note("2", "hi")
    assert store.remove_room("2") is True
    assert store.exits_from("1") == []
    assert store.exits_from("2") == []
    assert store.get_note("2") is None
    assert store.remove_room("2") is False


def test_areas_and_remove(store: MapStore) -> None:
    """An area removes its rooms."""
    store.add_area("a", "Area", ["x"], {"d": 1})
    store.upsert_room({"uid": "1", "area": "a"})
    store.upsert_room({"uid": "2", "area": "b"})
    area = store.get_area("a")
    assert area is not None
    assert area["flags"] == ["x"]
    assert [a["uid"] for a in store.list_areas()] == ["a"]
    assert store.remove_area("a") == ["1"]
    assert store.get_area("a") is None
    assert store.get_room("2") is not None


def test_unexplored_and_graph(store: MapStore) -> None:
    """Rooms with -1 exits are listed and the graph loads from the database."""
    store.upsert_room({"uid": "1", "area": "a", "flags": ["noportal"]})
    store.upsert_room({"uid": "2", "area": "b"})
    store.upsert_exit(Exit("1", "n", "-1"))
    store.upsert_exit(Exit("2", "s", "1", 2, {"r": 1}))
    assert [r["uid"] for r in store.unexplored()] == ["1"]
    assert store.unexplored("b") == []
    graph = store.load_graph()
    assert graph.room_flags("1") == {"noportal"}
    assert graph.exits_from("2") == [Exit("2", "s", "1", 2, {"r": 1})]
    assert json.loads(store.db.select("SELECT requirement FROM exits")[1]["requirement"]) == {
        "r": 1
    }


def test_room_differences() -> None:
    """Area changes and contradicting exits are reported; -1 and missing stored are not."""
    stored = {"uid": "1", "area": "a"}
    exits = [Exit("1", "n", "2"), Exit("1", "s", "3"), Exit("1", "e", "-1")]
    assert room_differences(None, [], {"uid": "1", "area": "z"}) == {}
    assert room_differences(stored, exits, {"uid": "1", "area": "a"}) == {}
    assert room_differences(stored, exits, {"uid": "1", "area": "b"}) == {"area": ("a", "b")}
    same = {"uid": "1", "exits": {"n": "2", "s": "-1", "e": "9"}}
    assert room_differences(stored, exits, same) == {}
    changed = room_differences(stored, exits, {"uid": "1", "exits": {"n": "7", "s": "3", "w": "4"}})
    assert changed["exits"] == {"n": ("2", "7"), "w": (None, "4"), "e": ("-1", None)}


def test_upsert_exit_keep_details(store: MapStore) -> None:
    """keep_details updates only the touid of an existing exit (#762)."""
    store.upsert_exit(Exit("1", "n", "2", 3, {"level": 100}))
    kept = store.upsert_exit(Exit("1", "n", "2"), keep_details=True)
    assert kept == Exit("1", "n", "2", 3, {"level": 100})
    assert store.upsert_exit(Exit("1", "n", "9"), keep_details=True) == Exit(
        "1", "n", "9", 3, {"level": 100}
    )
    assert store.upsert_exit(Exit("1", "n", "-1"), keep_details=True).touid == "9"
    # the default path still resets them
    assert store.upsert_exit(Exit("1", "n", "9")) == Exit("1", "n", "9", 1, None)
    # a new exit gets the given values
    assert store.upsert_exit(Exit("1", "s", "4", 2, {"k": 1}), keep_details=True) == Exit(
        "1", "s", "4", 2, {"k": 1}
    )
