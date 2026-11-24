"""Tests for the walk state machine."""

from bastproxy.plugins.client.mapper.libs._graph import Exit
from bastproxy.plugins.client.mapper.libs._walk import Walk

STEPS = [Exit("A", "n", "B"), Exit("B", "n", "C")]


def _started() -> Walk:
    walk = Walk()
    walk.start("C", STEPS, "A")
    return walk


def test_idle_ignores_arrivals() -> None:
    """A walk never starts on its own."""
    walk = Walk()
    assert walk.arrived("B").kind == "ignored"
    assert walk.state == "idle"


def test_steps_then_done() -> None:
    """Each confirmed arrival gives the next step, the last gives done."""
    walk = _started()
    update = walk.arrived("B")
    assert update.kind == "step"
    assert update.step == STEPS[1]
    assert walk.arrived("C").kind == "done"
    assert walk.state == "idle"
    assert walk.arrived("C").kind == "ignored"


def test_resent_room_is_ignored() -> None:
    """The room the step left from is ignored, at the start and after a step."""
    walk = _started()
    assert walk.arrived("A").kind == "ignored"
    walk.arrived("B")
    assert walk.arrived("B").kind == "ignored"
    assert walk.index == 1


def test_unexpected_reroute_and_stop() -> None:
    """An unexpected room is reported; reroute continues; stop keeps the target."""
    walk = _started()
    assert walk.arrived("Z").kind == "unexpected"
    walk.reroute([Exit("Z", "e", "C")], "Z")
    assert walk.reroutes == 1
    assert walk.current_step() == Exit("Z", "e", "C")
    assert walk.stop() is True
    assert walk.stop() is False
    assert walk.can_restart()
    assert walk.arrived("C").kind == "ignored"
    walk.restart([Exit("Z", "e", "C")], "Z")
    assert walk.state == "walking"
    assert walk.arrived("C").kind == "done"
    assert not walk.can_restart()


def test_as_dict() -> None:
    """as_dict has the documented keys."""
    data = _started().as_dict()
    assert set(data) == {"state", "target", "steps", "index", "reroutes"}
    assert data["steps"][0]["dir"] == "n"


def test_searching_state() -> None:
    """A search ignores arrivals, can be stopped and then restarted."""
    walk = _started()
    walk.searching("C", "A")
    assert walk.as_dict()["state"] == "searching"
    assert walk.steps == []
    assert walk.arrived("B").kind == "ignored"
    assert walk.stop() is True
    assert walk.state == "stopped"
    assert walk.can_restart()


def test_reroute_sets_walking() -> None:
    """A reroute after a search puts the walk back to walking."""
    walk = Walk()
    walk.start("C", STEPS, "A")
    walk.searching("C", "B")
    walk.reroute(STEPS[1:], "B")
    assert walk.state == "walking"
    assert walk.reroutes == 1
