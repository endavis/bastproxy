"""Tests for the mapper graph and pathfinder."""

from collections.abc import Callable

from bastproxy.plugins.client.mapper.libs._graph import Exit, MapGraph, find_path


def _graph() -> MapGraph:
    graph = MapGraph()
    for uid in "ABCDEF":
        graph.set_room(uid, ["noportal"] if uid == "B" else [])
    for exit_ in (
        Exit("A", "n", "B"),
        Exit("B", "n", "C"),
        Exit("A", "enter portal", "C", 5),
        Exit("C", "e", "D"),
        Exit("D", "e", "E", 1, {"level": 50}),
        Exit("A", "s", "E", 10),
        Exit("*", "portal f", "F"),
        Exit("**", "recall", "A"),
        Exit("E", "w", "-1"),
    ):
        graph.set_exit(exit_)
    return graph


def _allow(_: Exit) -> bool:
    return True


def _path(
    start: str,
    target: str,
    allowed: Callable[[Exit], bool] = _allow,
    depth: int = 300,
    graph: MapGraph | None = None,
) -> tuple[int, list[str]] | None:
    result = find_path(graph or _graph(), start, target, max_depth=depth, allowed=allowed)
    return None if result is None else (result.cost, [s.dir for s in result.steps])


def test_cheapest_path_wins() -> None:
    """A to C goes through B (cost 2), not the portal (5)."""
    assert _path("A", "C") == (2, ["n", "n"])


def test_requirement_blocks_and_allows() -> None:
    """A blocked exit falls back to the costly route; an allowed one is used."""
    blocked = _path("A", "E", allowed=lambda e: e.requirement is None)
    assert blocked == (10, ["s"])
    assert _path("A", "E") == (4, ["n", "n", "e", "e"])


def test_anywhere_exit_has_fromuid_star() -> None:
    """F is reached through the exit from anywhere."""
    result = find_path(_graph(), "A", "F", max_depth=5, allowed=_allow)
    assert result is not None
    assert [(s.fromuid, s.dir) for s in result.steps] == [("*", "portal f")]


def test_noportal_room_cannot_use_portals() -> None:
    """From B the portal is blocked, so the path leaves B first."""
    result = find_path(_graph(), "B", "F", max_depth=5, allowed=_allow)
    assert result is not None
    assert [s.dir for s in result.steps] == ["n", "portal f"]
    assert _path("B", "F", depth=1) is None


def test_norecall_room_cannot_recall() -> None:
    """A norecall room blocks the ** exits; another room can recall."""
    graph = _graph()
    graph.set_room("D", ["norecall"])
    assert _path("D", "A", depth=1, graph=graph) is None
    assert _path("D", "A", graph=graph) == (2, ["e", "recall"])
    assert _path("C", "A", graph=graph) == (1, ["recall"])


def test_unknown_start_uses_anywhere_exits() -> None:
    """A start that is not in the graph still has the anywhere exits."""
    assert _path("zzz", "F") == (1, ["portal f"])


def test_depth_limit() -> None:
    """The depth limit bounds the search."""
    assert _path("A", "E", depth=3) == (10, ["s"])
    assert _path("A", "E", depth=0) is None
    assert _path("A", "A", depth=0) == (0, [])


def test_start_is_target_and_unreachable() -> None:
    """The same room costs nothing; unreachable gives None; -1 exits are not used."""
    assert _path("A", "A") == (0, [])
    assert _path("E", "A", allowed=lambda e: e.dir != "recall") is None
    graph = _graph()
    graph.set_exit(Exit("E", "w", "-1"))
    assert _path("E", "E2", graph=graph) is None
    assert _path("E", "D", allowed=lambda e: e.dir != "recall", graph=graph) is None


def test_remove_room_and_exit() -> None:
    """Removing a room removes the exits to it."""
    graph = _graph()
    graph.remove_room("B")
    assert _path("A", "C", graph=graph) == (5, ["enter portal"])
    graph.remove_exit("A", "enter portal")
    assert _path("A", "C", graph=graph) is None
    assert not graph.has_room("B")


def test_exit_to_dict() -> None:
    """to_dict has the documented keys."""
    assert Exit("A", "n", "B", 2, {"x": 1}).to_dict() == {
        "fromuid": "A",
        "touid": "B",
        "dir": "n",
        "cost": 2,
        "requirement": {"x": 1},
    }
