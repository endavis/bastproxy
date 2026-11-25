# Project: bastproxy
# Filename: plugins/client/mapper/libs/_walk.py
#
# File Description: the walk state machine
#
# By: Bast
"""The walk state machine (ADR-0021).

A walk only moves when told a room was entered. It never starts by itself: ``start`` is
the only way out of ``idle``. This module imports nothing from bastproxy.
"""

from dataclasses import dataclass
from typing import Any, Literal

from ._graph import Exit

MAX_REROUTES = 3

IDLE = "idle"
SEARCHING = "searching"
WALKING = "walking"
STOPPED = "stopped"


@dataclass
class WalkUpdate:
    """What an arrival did to the walk.

    ``kind`` is ``ignored`` (nothing to do), ``step`` (send ``step`` now), ``done``
    (the target was reached) or ``unexpected`` (the character is somewhere else).
    """

    kind: Literal["ignored", "step", "done", "unexpected"]
    step: Exit | None = None


class Walk:
    """Where a step-by-step walk is, and what the next arrival means."""

    def __init__(self) -> None:
        """Initialize an idle walk."""
        self.state = IDLE
        self.target: str | None = None
        self.steps: list[Exit] = []
        self.index = 0
        self.reroutes = 0
        self._origin: str | None = None
        self.portals = True
        self.recalls = True

    def start(self, target: str, steps: list[Exit], from_uid: str) -> None:
        """Begin a walk. The caller sends the first step."""
        self.state = WALKING
        self.target = target
        self.steps = list(steps)
        self.index = 0
        self.reroutes = 0
        self._origin = from_uid

    def searching(
        self,
        target: str,
        from_uid: str,
        *,
        portals: bool = True,
        recalls: bool = True,
    ) -> None:
        """Wait for a path search. Arrivals are ignored until the walk is started again.

        ``portals`` and ``recalls`` are the path options the walk keeps for its reroutes.
        """
        self.portals = portals
        self.recalls = recalls
        self.state = SEARCHING
        self.target = target
        self.steps = []
        self.index = 0
        self._origin = from_uid

    def reroute(self, steps: list[Exit], from_uid: str) -> None:
        """Continue the walk with a new path from ``from_uid``."""
        self.state = WALKING
        self.steps = list(steps)
        self.index = 0
        self.reroutes += 1
        self._origin = from_uid

    def restart(self, steps: list[Exit], from_uid: str) -> None:
        """Walk the stored target again from ``from_uid``."""
        self.state = WALKING
        self.steps = list(steps)
        self.index = 0
        self._origin = from_uid

    def arrived(self, uid: str) -> WalkUpdate:
        """Handle the character being in room ``uid``."""
        if self.state != WALKING or self.index >= len(self.steps):
            return WalkUpdate("ignored")
        if uid == self._origin:
            return WalkUpdate("ignored")
        if uid != self.steps[self.index].touid:
            return WalkUpdate("unexpected")
        self.index += 1
        self._origin = uid
        if self.index >= len(self.steps):
            self.state = IDLE
            return WalkUpdate("done")
        return WalkUpdate("step", self.steps[self.index])

    def current_step(self) -> Exit | None:
        """Return the step waiting for its arrival, if walking."""
        if self.state == WALKING and self.index < len(self.steps):
            return self.steps[self.index]
        return None

    def finish(self) -> None:
        """End the walk as done."""
        self.state = IDLE

    def stop(self) -> bool:
        """Stop a walk or a search, keeping the target. Returns False when neither is active."""
        if self.state not in (WALKING, SEARCHING):
            return False
        self.state = STOPPED
        return True

    def can_restart(self) -> bool:
        """Check if a stopped walk has a target to resume."""
        return self.state == STOPPED and self.target is not None

    def as_dict(self) -> dict[str, Any]:
        """Return the walk as a plain dict."""
        return {
            "state": self.state,
            "target": self.target,
            "steps": [step.to_dict() for step in self.steps],
            "index": self.index,
            "reroutes": self.reroutes,
        }
