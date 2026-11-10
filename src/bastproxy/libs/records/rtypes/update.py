# Project: bastproxy
# Filename: libs/records/rtypes/update.py
#
# File Description: Holds the display view of a record update
#
# By: Bast
"""Holds the display view of a record update.

``TrackedUpdate`` wraps a pydatatracker ``ChangeLogEntry`` and gives it the interface that
``#bp.debug.records`` shows: a uuid, a flag, an action, an actor and a detailed format. Every
record type shows its updates through it, whether the entry came from a pydatatracker
container or from ``BaseRecord.addupdate``.
"""

# Standard Library
import datetime
import pprint
from typing import Any

# 3rd Party
from pydatatracker.utils.changelog import ChangeLogEntry

# Project
from bastproxy.libs.context import get_command_args
from bastproxy.libs.records.enums import UpdateFlag
from bastproxy.libs.records.managers.records import next_creation_sequence

__all__ = [
    "INFO_ACTIONS",
    "RESERVED_KEYS",
    "TrackedUpdate",
]

# Entries pydatatracker creates itself carry no flag. These actions are informational.
INFO_ACTIONS = frozenset({"init", "lock", "unlock"})
# Keys of a change entry that are not part of the caller's ``extra``.
_ENTRY_KEYS = frozenset({"action", "flag", "type", "locked", "event_stack"})
# Keys that pydatatracker or the update reads itself, so a caller's ``extra`` may not use them.
RESERVED_KEYS = frozenset(
    {"action", "flag", "type", "locked", "actor", "location", "method", "event_stack"}
)
# Separates event names in the ``event_stack`` entry key.
EVENT_STACK_SEPARATOR = " > "


class TrackedUpdate:
    """A read-only view of a pydatatracker ``ChangeLogEntry``."""

    def __init__(self, parent: Any, entry: ChangeLogEntry) -> None:
        """Wrap a change entry.

        Args:
            parent: The record that owns the entry.
            entry: The pydatatracker change entry to show.

        """
        self.entry = entry
        self.parent = parent
        # The sequence lives on the entry, so every view of it agrees. Entries made by
        # ``BaseRecord.addupdate`` get it at creation; a pydatatracker entry gets it the
        # first time it is viewed, as the library offers no hook (its own timestamps
        # never tie).
        if not hasattr(entry, "creation_sequence"):
            entry.creation_sequence = next_creation_sequence()

    @property
    def creation_sequence(self) -> int:
        """The process-wide creation sequence number of the entry."""
        return int(self.entry.creation_sequence)

    @property
    def uuid(self) -> str:
        """The entry's uuid."""
        return self.entry.uuid

    @property
    def time_taken(self) -> datetime.datetime:
        """When the entry was created."""
        return self.entry.created_time

    @property
    def action(self) -> str:
        """What the entry records."""
        return str(self.entry.extra.get("action", ""))

    @property
    def flag(self) -> str:
        """The entry's flag, one of 'Modify', 'Set Flag' or 'Info'."""
        if flag := self.entry.extra.get("flag"):
            return str(flag)
        return UpdateFlag.INFO if self.action in INFO_ACTIONS else UpdateFlag.MODIFY

    @property
    def extra(self) -> dict[str, Any]:
        """Everything on the entry except the keys that have their own property."""
        return {k: v for k, v in self.entry.extra.items() if k not in _ENTRY_KEYS}

    @property
    def data(self) -> Any:
        """The entry's data, which a tracked update does not keep."""
        return None

    @property
    def actor(self) -> str:
        """The actor context name the change ran under, or an empty string."""
        return str(self.entry.actor or "")

    @property
    def event_stack(self) -> list[str]:
        """The events being raised when the update was made, outermost first."""
        stack = self.entry.extra.get("event_stack")
        return str(stack).split(EVENT_STACK_SEPARATOR) if stack else []

    @property
    def stack(self) -> list[str]:
        """The stack captured with the entry, empty unless stack capture is on."""
        return list(self.entry.stack)

    def __hash__(self) -> int:
        """Hash by class name and uuid."""
        return hash(f"{self.__class__.__name__}:{self.uuid}")

    def __eq__(self, other: object) -> bool:
        """Equal when both are tracked updates with the same uuid."""
        return isinstance(other, TrackedUpdate) and self.uuid == other.uuid

    def __lt__(self, other: Any) -> bool:
        """Order by creation time, then by creation sequence when the times tie."""
        if self.time_taken != other.time_taken:
            return bool(self.time_taken < other.time_taken)
        return self.creation_sequence < other.creation_sequence

    def __str__(self) -> str:
        """Return the flag, action and extra."""
        return f"{self.flag} - {self.action} - {self.data} - {self.extra}"

    def format_detailed(
        self,
        show_data: bool = False,
        show_stack: bool = False,
        data_lines_to_show: int = 10,
    ) -> list[str]:
        """Format the entry for the detail view."""
        args = get_command_args()
        if "show_data" in args:
            show_data = args["show_data"]
        if "show_stack" in args:
            show_stack = args["show_stack"]
        if "data_lines_to_show" in args:
            data_lines_to_show = int(args["data_lines_to_show"])

        tmsg = [
            f"{'UUID':<15} : {self.uuid}",
            f"{'Record':<15} : {self.parent.__class__.__name__}:{self.parent.uuid}",
            f"{'Flag':<15} : {self.flag}",
            f"{'Actor':<15} : {self.actor or 'Unknown'}",
            f"{'Action':<15} : {self.action}",
            f"{'Time Taken':<15} : {self.time_taken}",
        ]
        if extra := self.extra:
            tmsg.append(f"{'Extra':<15} : {extra}")
        if event_stack := self.event_stack:
            tmsg.append(f"{'Event Stack':<15} :")
            tmsg.extend(f"{'':<15} : {event}" for event in event_stack)
        if show_data and self.data is not None:
            data = self.data
            if isinstance(data, list) and data_lines_to_show != -1:
                data = data[:data_lines_to_show]
            tmsg.append(f"{'Data':<15} :")
            tmsg.extend(
                f"{'':<15} : {line}" for line in pprint.pformat(data, width=120).splitlines()
            )
        if show_stack and self.stack:
            tmsg.append(f"{'Stack':<15} :")
            tmsg.extend([f"{'':<15} {line}" for line in self.stack if line.strip()])
        return tmsg
