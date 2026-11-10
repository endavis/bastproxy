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

``TrackedUpdate`` (in ``rtypes/update.py``, re-exported here) wraps a pydatatracker
``ChangeLogEntry`` and gives it the display interface ``#bp.debug.records`` shows.

See ADR-0006 and ``docs/claude/record_system.md``.
"""

# Standard Library
import datetime
from typing import Any, ClassVar

# 3rd Party
from pydatatracker import tracking_actor

# Project
from bastproxy.libs.records.enums import UpdateFlag
from bastproxy.libs.records.managers.records import DEFAULT_MAX_CHANGES, RMANAGER
from bastproxy.libs.records.rtypes.base import RecordDisplayMixin
from bastproxy.libs.records.rtypes.update import RESERVED_KEYS, TrackedUpdate

__all__ = [
    "MAX_CHANGES",
    "TrackedRecordMixin",
    "TrackedUpdate",
    "current_capture_stacks",
    "current_max_changes",
    "tracking_actor",
]

# Default cap on the change entries a record keeps. The cap in force is
# ``RMANAGER.max_changes``, set by the ``tracking_max_changes`` setting.
MAX_CHANGES = DEFAULT_MAX_CHANGES


def current_max_changes() -> int:
    """Return the cap on change entries that a new record gets."""
    return RMANAGER.max_changes


def current_capture_stacks() -> bool:
    """Return whether new records capture call stacks (the ``capture_stacks`` setting)."""
    return RMANAGER.capture_stacks


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
        flag: UpdateFlag | str,
        action: str,
        extra: dict[str, Any] | None = None,
        savedata: bool = False,
    ) -> None:
        """Add a change entry for this record.

        Args:
            flag: an ``UpdateFlag`` or its string ('Modify', 'Set Flag', 'Info'); an unknown
                value raises ``ValueError``.
            action: a description of what was changed.
            extra: any extra info about the change.
            savedata: accepted for the old interface; a tracked update keeps no data.

        """
        del savedata  # kept so callers passing savedata= still work
        flag = UpdateFlag(flag)
        kwargs = {
            (f"extra_{key}" if key in RESERVED_KEYS else key): value
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
