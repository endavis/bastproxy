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


# ---- web page queries (#766) ----


def _fill(store: MapStore) -> None:
    store.add_area("a", "Alpha", [], {})
    store.add_area("empty", "Empty", [], {})
    for uid, name, area in [("1", "Main Hall", "a"), ("2", "Cellar", "a"), ("3", "Hall 100%", "b")]:
        store.upsert_room({"uid": uid, "name": name, "area": area})
    store.upsert_exit(Exit("1", "n", "2"))
    store.upsert_exit(Exit("1", "e", "-1"))
    store.upsert_exit(Exit("1", "w", "-1"))


def test_area_counts(store: MapStore) -> None:
    _fill(store)
    store.upsert_room({"uid": "4", "name": "Lost", "area": ""})
    assert store.area_counts() == [
        {"uid": "a", "name": "Alpha", "rooms": 2, "unexplored": 1},
        {"uid": "b", "name": "", "rooms": 1, "unexplored": 0},
        {"uid": "empty", "name": "Empty", "rooms": 0, "unexplored": 0},
    ]


def test_get_rooms_over_the_chunk_size(store: MapStore) -> None:
    for number in range(1200):
        store.upsert_room({"uid": str(number), "name": f"r{number}"})
    found = store.get_rooms([str(n) for n in range(1200)] + ["missing"])
    assert len(found) == 1200
    assert found["1199"]["name"] == "r1199"
    assert store.get_rooms([]) == {}


def test_search_rooms_name_sort_and_paging(store: MapStore) -> None:
    _fill(store)
    rooms, total = store.search_rooms("hall")
    assert (total, [r["uid"] for r in rooms]) == (2, ["1", "3"])
    rooms, total = store.search_rooms("", sort="name", descending=True, limit=2, offset=1)
    assert (total, [r["uid"] for r in rooms]) == (3, ["3", "2"])
    rooms, _ = store.search_rooms("", filters={"area": "a", "bogus": "x", "name": ""})
    assert [r["uid"] for r in rooms] == ["1", "2"]
    assert store.search_rooms("", sort="not a column; DROP TABLE rooms")[1] == 3


def test_search_rooms_like_wildcards_are_literal(store: MapStore) -> None:
    _fill(store)
    store.upsert_room({"uid": "5", "name": "a_b\\c"})
    assert [r["uid"] for r in store.search_rooms("100%")[0]] == ["3"]
    assert store.search_rooms("%")[1] == 1
    assert [r["uid"] for r in store.search_rooms("_b\\")[0]] == ["5"]
    assert store.search_rooms("Hall_")[1] == 0


def test_search_rooms_injection_like_text_matches_nothing(store: MapStore) -> None:
    _fill(store)
    for text in ["' OR 1=1 --", "x'; DROP TABLE rooms; --"]:
        assert store.search_rooms(text) == ([], 0)
        assert store.search_rooms("", filters={"name": text}) == ([], 0)
    assert store.search_rooms("")[1] == 3


# ---- mismatch handling (#795, #796, #797) ----


def test_room_differences_custom_exit_is_not_removed() -> None:
    """A stored custom exit the update lacks is not reported; a plain one is (#795)."""
    stored = {"uid": "1", "area": "a"}
    exits = [
        Exit("1", "n", "101"),
        Exit("1", "open door;wait(2);north", "105"),
        Exit("1", "north", "106"),
        Exit("1", "enter portal", "107"),
    ]
    assert room_differences(stored, exits[:2], {"uid": "1", "exits": {"n": "101"}}) == {}
    found = room_differences(stored, exits, {"uid": "1", "exits": {"n": "101"}})
    assert found == {"exits": {"north": ("106", None)}}


def test_room_differences_fields() -> None:
    """name, terrain and coordinates are reported; missing or None values are not."""
    stored = {"uid": "1", "name": "Hall", "terrain": "city", "x": 1, "y": 2, "z": 3}
    update = {"uid": "1", "name": "Big Hall", "terrain": None, "x": 1, "y": 5}
    assert room_differences(stored, [], update) == {
        "name": ("Hall", "Big Hall"),
        "y": (2, 5),
    }


def test_room_differences_details_common_keys_only() -> None:
    """details compares the keys both sides have."""
    stored = {"uid": "1", "details": {"details": "x", "old": 1}}
    update = {"uid": "1", "details": {"details": "y", "coord_id": 4, "old": 1}}
    assert room_differences(stored, [], update) == {"details": {"details": ("x", "y")}}
    assert room_differences(stored, [], {"uid": "1", "details": {"new": 1}}) == {}


def test_room_differences_area_needs_both_sides() -> None:
    """An empty stored area or a missing, None or empty update area is no difference."""
    assert room_differences({"uid": "1", "area": ""}, [], {"uid": "1", "area": "a"}) == {}
    stored = {"uid": "1", "area": "a"}
    for update in ({"uid": "1"}, {"uid": "1", "area": None}, {"uid": "1", "area": ""}):
        assert room_differences(stored, [], update) == {}


def test_room_differences_ignoreexits_flag() -> None:
    """A flagged room skips the exits but still reports the area (#797)."""
    stored = {"uid": "1", "area": "a", "flags": ["ignoreexits"]}
    update = {"uid": "1", "area": "b", "exits": {"n": "9"}}
    assert room_differences(stored, [Exit("1", "n", "2")], update) == {"area": ("a", "b")}


def test_set_room_flags(store: MapStore) -> None:
    """set_room_flags writes only the flags, and load_graph sees them."""
    store.upsert_room({"uid": "1", "name": "Hall", "area": "a", "x": 4, "flags": ["shop"]})
    assert store.set_room_flags("1", ["shop", "ignoreexits"]) is True
    assert store.set_room_flags("zz", ["x"]) is False
    room = store.get_room("1")
    assert room is not None
    assert (room["name"], room["area"], room["x"]) == ("Hall", "a", 4)
    assert room["flags"] == ["shop", "ignoreexits"]
    assert store.load_graph().room_flags("1") == frozenset({"shop", "ignoreexits"})
