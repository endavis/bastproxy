# Project: bastproxy
# Filename: libs/records/tracking.py
#
# File Description: Adapts pydatatracker containers to the record interface
#
# By: Bast
"""Adapt pydatatracker containers to the record interface.

``TrackedRecordMixin`` goes in front of a pydatatracker base class (``TrackedAttr``,
``TrackedList``) and gives it the record interface the rest of the proxy uses: a
``uuid``, ``created``, ``parent`` and ``parents``, identity by uuid, registration with
``RMANAGER`` and an ``updates`` view over the object's change log.

``TrackedUpdate`` wraps a pydatatracker ``ChangeLogEntry`` and gives it the display
interface of ``UpdateRecord``, so ``#bp.debug.records`` needs no changes.

See ADR-0006 and ``docs/claude/record_system.md``.
"""

# Standard Library
import datetime
import pprint
from typing import Any, ClassVar

# 3rd Party
from pydatatracker import tracking_actor
from pydatatracker.utils.changelog import ChangeLogEntry

# Project
from bastproxy.libs.api import API
from bastproxy.libs.records.managers.records import DEFAULT_MAX_CHANGES, RMANAGER
from bastproxy.libs.records.rtypes.base import RecordDisplayMixin

__all__ = [
    "MAX_CHANGES",
    "TrackedRecordMixin",
    "TrackedUpdate",
    "current_max_changes",
    "tracking_actor",
]

# Default cap on the change entries a record keeps. The cap in force is
# ``RMANAGER.max_changes``, set by the ``tracking_max_changes`` setting.
MAX_CHANGES = DEFAULT_MAX_CHANGES


def current_max_changes() -> int:
    """Return the cap on change entries that a new record gets."""
    return RMANAGER.max_changes


# Entries pydatatracker creates itself carry no flag. These actions are informational.
_INFO_ACTIONS = frozenset({"init", "lock", "unlock"})
# Keys of a change entry that are not part of the caller's ``extra``.
_ENTRY_KEYS = frozenset({"action", "flag", "type", "locked"})
# Keys that pydatatracker reads itself, so a caller's ``extra`` may not use them.
_RESERVED_KEYS = frozenset({"action", "flag", "type", "locked", "actor", "location", "method"})

_STAND_IN_API = API(owner_id="TrackedUpdate")


class TrackedUpdate:
    """A read-only view of a pydatatracker ``ChangeLogEntry`` shaped like an ``UpdateRecord``."""

    def __init__(self, parent: Any, entry: ChangeLogEntry) -> None:
        """Wrap a change entry.

        Args:
            parent: The record that owns the entry.
            entry: The pydatatracker change entry to show.

        """
        self.entry = entry
        self.parent = parent
        self.api = _STAND_IN_API
        self.event_stack: list[str] = []

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
        return "Info" if self.action in _INFO_ACTIONS else "Modify"

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
        """Order by creation time."""
        return bool(self.time_taken < other.time_taken)

    def __str__(self) -> str:
        """Return the flag, action and extra."""
        return f"{self.flag} - {self.action} - {self.data} - {self.extra}"

    def format_detailed(
        self,
        show_data: bool = False,
        show_stack: bool = False,
        data_lines_to_show: int = 10,
    ) -> list[str]:
        """Format the entry like ``UpdateRecord.format_detailed``."""
        args = self.api("plugins.core.commands:command.current.args.get")()
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


class TrackedRecordMixin(RecordDisplayMixin):
    """The record interface for a class built on a pydatatracker container.

    Put this first in the bases, for example ``class NetworkData(TrackedRecordMixin,
    TrackedList)``, so its ``__eq__`` and ``__hash__`` win over the container's.
    """

    # A data holder never starts a root tree; it joins the tree of whatever adopts it.
    retention_root: ClassVar[bool] = False

    execute_time_taken: int = -1
    owner_id: str
    parent: Any
    parents: list[Any]

    # --- identity ---------------------------------------------------------------------

    @property
    def uuid(self) -> str:
        """The record's identity, the pydatatracker uuid."""
        return str(self._tracking_uuid)  # type: ignore[attr-defined]

    @property
    def created(self) -> datetime.datetime:
        """When the record was created."""
        return self.tracking_created  # type: ignore[attr-defined, no-any-return]

    def _init_record(self, owner_id: str = "", parent: Any = None) -> None:
        """Set the record fields and register with ``RMANAGER``.

        Call after the pydatatracker base ``__init__``, which creates the uuid.

        Args:
            owner_id: The owner id, per class by default so API stats stay bounded (#232).
            parent: The parent record; defaults to the record being executed.

        """
        self.owner_id = owner_id or self.__class__.__name__
        if not parent:
            parent = RMANAGER.get_latest_record()
        self.parent = parent
        self.parents = []
        if parent:
            self.add_parent(parent)
        RMANAGER.add(self)

    def add_parent(self, parent: Any, reset: bool = False) -> None:
        """Add a parent to this record."""
        if reset:
            self.parents = []
        if parent not in self.parents:
            self.parents.append(parent)

    def __hash__(self) -> int:
        """Hash by class name and uuid."""
        return hash(f"{self.__class__.__name__}:{self.uuid}")

    def __eq__(self, other: object) -> bool:
        """Equal when both are tracked records with the same uuid."""
        return isinstance(other, TrackedRecordMixin) and self.uuid == other.uuid

    def __ne__(self, other: object) -> bool:
        """Not equal, defined here so a container's content-based ``__ne__`` does not win."""
        return not self.__eq__(other)

    def __repr__(self) -> str:
        """Return the class name and uuid."""
        return f"{self.__class__.__name__}:{self.uuid}"

    def __lt__(self, other: Any) -> bool:
        """Order by creation time."""
        return bool(self.created < other.created)

    # --- updates ----------------------------------------------------------------------

    def addupdate(
        self,
        flag: str,
        action: str,
        extra: dict[str, Any] | None = None,
        savedata: bool = False,
    ) -> None:
        """Add a change entry for this record.

        Args:
            flag: one of 'Modify', 'Set Flag', 'Info'.
            action: a description of what was changed.
            extra: any extra info about the change.
            savedata: accepted for the old interface; a tracked update keeps no data.

        """
        kwargs = {
            (f"extra_{key}" if key in _RESERVED_KEYS else key): value
            for key, value in (extra or {}).items()
        }
        self.tracking_create_change(action=action, flag=flag, **kwargs)  # type: ignore[attr-defined]

    @property
    def updates(self) -> list[TrackedUpdate]:
        """A view of this record's own change entries.

        pydatatracker re-homes every child entry onto its parent. An entry made here has a
        tree of one item and a re-homed one has two or more, so only the first kind is
        shown, and a parent's ``get_all_updates`` does not show a child's change twice.
        """
        return [
            TrackedUpdate(self, entry)
            for entry in self.tracking_changes()  # type: ignore[attr-defined]
            if len(entry.tree) == 1
        ]

    def get_update(self, uuid: str) -> TrackedUpdate | None:
        """Get one of this record's own updates by uuid."""
        return next((update for update in self.updates if update.uuid == uuid), None)

    def get_all_updates(self, update_filter: list[str] | None = None) -> list[Any]:
        """Get the updates of this record and all of its child records, in time order."""
        update_filter = update_filter or []
        updates: list[Any] = []
        for record in RMANAGER.get_all_children_list(self, record_filter=update_filter):
            updates.extend(
                update
                for update in record.updates
                if update.parent.__class__.__name__ not in update_filter
            )
        updates.extend(self.updates)
        return sorted(set(updates))
