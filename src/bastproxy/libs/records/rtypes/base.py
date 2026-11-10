# Project: bastproxy
# Filename: libs/records/rtypes/base.py
#
# File Description: Holds the base record type
#
# By: Bast
"""Holds the base record type."""

# Standard Library
import datetime
import inspect
import pprint
import traceback
from collections import deque
from types import FrameType
from typing import Any, ClassVar
from uuid import uuid4

# 3rd Party
# Project
from pydatatracker.types.actor import current_actor
from pydatatracker.utils.changelog import ChangeLogEntry

from bastproxy.libs.api import API
from bastproxy.libs.context import event_stack
from bastproxy.libs.logger import get_logger
from bastproxy.libs.records.enums import UpdateFlag
from bastproxy.libs.records.managers.records import RMANAGER, next_creation_sequence
from bastproxy.libs.records.rtypes.update import (
    EVENT_STACK_SEPARATOR,
    RESERVED_KEYS,
    TrackedUpdate,
)

logger = get_logger(__name__)

# Stack frames kept when stack capture is on.
CREATION_STACK_LIMIT = 10
UPDATE_STACK_LIMIT = 15

_RECORDS_PACKAGE = "bastproxy.libs.records"


def _caller_actor() -> str:
    """Name the innermost caller outside the records package, as ``module:function``.

    This is the actor for an update made with no tracking actor set, such as on the MUD and
    client data paths. It walks frame objects only, so it costs far less than formatting a
    stack.
    """
    current = inspect.currentframe()
    frame: FrameType | None = current.f_back if current else None
    while frame is not None:
        module = str(frame.f_globals.get("__name__", ""))
        if module != _RECORDS_PACKAGE and not module.startswith(f"{_RECORDS_PACKAGE}."):
            return f"{module}:{frame.f_code.co_name}"
        frame = frame.f_back
    return ""


class RecordDisplayMixin:
    """Display code shared by every record class.

    The two hooks ``_monitored_fields`` and ``_original_value`` and the creation-info hook
    ``_format_creation_info`` let ``BaseRecord`` and the pydatatracker-backed records format
    the same way. A class provides ``updates``, a list of ``TrackedUpdate``; the shared
    ``get_update`` and ``get_all_updates`` build on it.
    """

    column_width: int = 15

    def _monitored_fields(self) -> list[str]:
        """Return the names of the monitored fields to show in the details."""
        raise NotImplementedError

    def _original_value(self, name: str) -> Any:
        """Return the value a monitored field had when it was first set."""
        raise NotImplementedError

    def _format_creation_info(self) -> list[str]:
        """Return the detail lines that describe how the record was created."""
        return []

    def get_all_updates(self, update_filter=None) -> list[Any]:
        """Get the updates of this record and all of its child records, in time order."""
        update_filter = update_filter or []
        updates: list[Any] = []
        for record in RMANAGER.get_all_children_list(self, record_filter=update_filter):
            updates.extend(
                update
                for update in record.updates
                if update.parent.__class__.__name__ not in update_filter
            )
        updates.extend(self.updates)  # type: ignore[attr-defined]
        return sorted(set(updates))

    def get_update(self, uuid: str) -> Any:
        """Get an update by uuid: one of this record's own, then one of its children's."""
        for update in self.updates:  # type: ignore[attr-defined]
            if update.uuid == uuid:
                return update
        for child in RMANAGER.get_all_children_list(self):
            for update in child.updates:
                if update.uuid == uuid:
                    return update
        return None

    def get_attributes_to_format(self):
        """Attributes to format in the details.

        0 will be the top section
        1 is the middle section
        3 is the bottom section.
        """
        default_attributes = {
            0: [
                ("UUID", "uuid"),
                ("Owner ID", "owner_id"),
                ("Creation Time", "created"),
                ("Parent", "parent"),
                ("Parents", "parents"),
                ("Exec Time (ms)", "execute_time_taken"),
            ],
            1: [],
            2: [],
        }

        for item in self._monitored_fields():
            orig_value = self._original_value(item)
            if orig_value == getattr(self, item):
                default_attributes[0].append((f"{item}", item))
            else:
                default_attributes[0].append(
                    (
                        item,
                        f"changed from '{orig_value!r}' to '{getattr(self, item)!r}'",
                    )
                )

        return default_attributes

    def format_children(self, full_children_records=False, update_filter=None):
        """Format children records as a string representation.

        Args:
            full_children_records: Include full record details if True.
            update_filter: Optional filter for update types to include.

        Returns:
            A list of formatted strings representing child records.

        """
        msg = []
        if full_children_records:
            children_records = RMANAGER.get_all_children_dict(self, record_filter=update_filter)
            msg.extend(["Children Records :", "---------------------------------------"])
            for record in children_records:
                msg.extend(
                    f"     {line}"
                    for line in record.get_formatted_details(
                        full_children_records=False,
                        include_updates=False,
                        update_filter=update_filter,
                        include_children_records=False,
                    )
                )
                msg.append("---------------------------------------")
        else:
            msg.extend(
                [
                    "Children Records :",
                    *RMANAGER.format_all_children(self, record_filter=update_filter),
                ]
            )
        return msg

    def get_formatted_details(
        self,
        full_children_records=False,
        include_updates=True,
        update_filter=None,
        include_children_records=True,
    ) -> list[str]:
        """Get a formatted detail string."""
        column_width = 15
        msg = [
            f"{'Type':<{column_width}} : {self.__class__.__name__}",
        ]

        attributes = self.get_attributes_to_format()
        for level in attributes:
            for item_string, item_attr in attributes[level]:
                if isinstance(item_attr, str):
                    attr = getattr(self, item_attr) if hasattr(self, item_attr) else item_attr
                else:
                    attr = item_attr
                if isinstance(attr, (list, dict)):
                    msg.append(f"{item_string:<{self.column_width}} : ")
                    msg.extend(
                        f"{'':<15} : {line}"
                        for line in pprint.pformat(attr, width=120).splitlines()
                    )
                else:
                    msg.append(f"{item_string:<{self.column_width}} : {attr}")

        msg.extend(self._format_creation_info())
        if include_children_records:
            msg.extend(self.format_children(full_children_records, update_filter))
        if include_updates:
            msg.extend(
                [
                    "Updates :",
                    "-------------------------",
                ]
            )
            for update in self.get_all_updates(update_filter):
                msg.extend([f"   {line}" for line in update.format_detailed()])
                msg.append("-------------------------")
        return msg


class BaseRecord(RecordDisplayMixin):
    """Base class for the processing records.

    A plain tree node: a unique id, a parent and parents, execution timing and a capped list
    of updates. It watches no attributes and intercepts no assignments. Each update is a
    pydatatracker ``ChangeLogEntry`` made by ``addupdate``, and the context (the actor, the
    event stack) comes from context variables, so recording one makes no API call.

    Call stacks are captured only while ``RMANAGER.capture_stacks`` is on.
    """

    # A parentless record of this class starts a root tree that the records manager counts
    # and evicts whole.
    retention_root: ClassVar[bool] = True

    def __init__(self, owner_id: str = "", track_record=True, parent=None):
        """Initialize the class."""
        # create a unique id for this message
        self.uuid = uuid4().hex
        # The owner id is per class, not per record, so API stats stay bounded (#232).
        # The uuid is the record identity.
        self.owner_id = owner_id or self.__class__.__name__
        # Add an API
        self.api = API(owner_id=self.owner_id)
        self.created = datetime.datetime.now(datetime.UTC)
        self._creation_sequence = next_creation_sequence()
        self._updates: deque[ChangeLogEntry] = deque(maxlen=RMANAGER.max_changes)
        self.execute_time_taken = -1
        self.track_record = track_record
        self.column_width = 15
        self.stack_at_creation: list[str] = (
            self._format_stack(CREATION_STACK_LIMIT) if RMANAGER.capture_stacks else []
        )
        self.event_stack: tuple[str, ...] = event_stack.get()

        if not parent:
            parent = RMANAGER.get_latest_record()
        self.parent = parent
        self.parents = []
        if parent:
            self.add_parent(parent)

        RMANAGER.add(self)
        self.executing = False

    @staticmethod
    def _format_stack(limit: int) -> list[str]:
        """Return the current call stack as a list of lines, without this helper's own frame."""
        lines: list[str] = []
        for frame in traceback.format_stack(limit=limit + 1)[:-1]:
            lines.extend(line for line in frame.splitlines() if line)
        return lines

    def add_parent(self, parent, reset=False):
        """Add a parent to this record."""
        if reset:
            self.parents = []
        if parent not in self.parents:
            self.parents.append(parent)

    def __hash__(self):
        """Return hash based on class name and UUID.

        Returns:
            Hash value for the record.

        """
        return hash(f"{self.__class__.__name__}:{self.uuid}")

    def __eq__(self, other):
        """Check equality based on UUID.

        Args:
            other: The other object to compare with.

        Returns:
            True if UUIDs match, False otherwise.

        """
        return self.uuid == other.uuid if isinstance(other, BaseRecord) else False

    def __repr__(self):
        """Return string representation of the record.

        Returns:
            String in format ClassName:UUID.

        """
        return f"{self.__class__.__name__}:{self.uuid}"

    def __lt__(self, other):
        """Compare records by creation time, then creation sequence when the times tie.

        Args:
            other: The other record to compare with.

        Returns:
            True if this record was created before the other.

        """
        if self.created != other.created:
            return self.created < other.created
        return self._creation_sequence < other._creation_sequence

    def one_line_summary(self):
        """Get a one line summary of the record."""
        if self.execute_time_taken > 0:
            return f"{self.__class__.__name__:<20} {self.uuid} {self.owner_id} {self.execute_time_taken:.2f}ms"
        return f"{self.__class__.__name__:<20} {self.uuid} {self.owner_id}"

    def addupdate(self, flag: UpdateFlag | str, action: str, extra: dict | None = None):
        """Add an update for this record.

            flag: an ``UpdateFlag`` or its string ('Modify', 'Set Flag', 'Info');
                an unknown value raises ``ValueError``
            action: a description of what was changed
            extra: any extra info about this change
        The actor is the current tracking actor or, with none set, the innermost caller
        outside the records package. The event stack is the events being raised.
        The call stack is captured only while ``RMANAGER.capture_stacks`` is on.
        a message should create an update at the following times:
            when it is created
            after modification
            when it ends up at it's destination.
        """
        flag = UpdateFlag(flag)
        kwargs = {
            (f"extra_{key}" if key in RESERVED_KEYS else key): value
            for key, value in (extra or {}).items()
        }
        if stack := event_stack.get():
            kwargs["event_stack"] = EVENT_STACK_SEPARATOR.join(stack)
        entry = ChangeLogEntry(
            self.uuid,
            capture_stack=False,
            actor=current_actor.get() or _caller_actor(),
            action=action,
            flag=flag,
            **kwargs,
        )
        if RMANAGER.capture_stacks:
            entry.stack = self._format_stack(UPDATE_STACK_LIMIT)
        entry.creation_sequence = next_creation_sequence()
        self._updates.append(entry)

    @property
    def updates(self) -> list[TrackedUpdate]:
        """A view of this record's own updates, oldest first."""
        return [TrackedUpdate(self, entry) for entry in self._updates]

    def _monitored_fields(self) -> list[str]:
        """Return the names of the monitored fields to show in the details, none."""
        return []

    def _original_value(self, name: str) -> Any:
        """Return the value a monitored field had when it was first set, none are monitored."""
        return None

    def _format_creation_info(self) -> list[str]:
        """Return the event stack and call stack the record was created under."""
        lines = [
            "Event Stack at Creation :",
            *[f"    {event}" for event in self.event_stack],
        ]
        if self.stack_at_creation:
            lines.append("Call Stack at Creation :")
            lines.extend(f"    {line}" for line in self.stack_at_creation)
        else:
            lines.append(
                "Call Stack at Creation : not captured (set capture_stacks in plugins.debug.records)"
            )
        return lines

    # def __str__(self):
    #     return f"{self.__class__.__name__}:{self.uuid})"

    def _exec_(self, *args, **kwargs):
        """Override this in the derived classes if needed."""
        raise NotImplementedError

    def __call__(self, *args, **kwargs):
        """Enable tracking of the class execution."""
        actor = kwargs.get("actor", "Unknown")
        if self.executing:
            self.addupdate(
                UpdateFlag.INFO,
                f"{self.__class__.__name__} already executing",
                extra={"actor": actor},
            )
            return

        self.executing = True

        self.addupdate(UpdateFlag.INFO, f"{self.__class__.__name__} _exec_ start")

        try:
            if self.track_record:
                tracking_uuid = self.api("libs.timing:timing.start")(
                    f"{self.__class__.__name__}:{self.uuid}.__call__"
                )
                RMANAGER.start(self)
                try:
                    self._exec_(*args, **kwargs)
                finally:
                    RMANAGER.end(self)
                    self.execute_time_taken = self.api("libs.timing:timing.finish")(tracking_uuid)
            else:
                self._exec_(*args, **kwargs)

            self.addupdate(UpdateFlag.INFO, f"{self.__class__.__name__} _exec_ finish")
        finally:
            self.executing = False


def __getattr__(name: str) -> Any:
    """Re-export ``BaseDictRecord`` lazily.

    ``dictrecord`` imports ``tracking``, which imports this module, so a top-level import
    would be circular.
    """
    if name == "BaseDictRecord":
        from bastproxy.libs.records.rtypes.dictrecord import BaseDictRecord

        return BaseDictRecord
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
