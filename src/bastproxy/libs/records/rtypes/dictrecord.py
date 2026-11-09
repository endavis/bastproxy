# Project: bastproxy
# Filename: libs/records/rtypes/dictrecord.py
#
# File Description: Holds the base record type for dictionary records
#
# By: Bast
"""Holds the dictionary record base class.

``BaseDictRecord`` is a pydatatracker ``TrackedDict`` with the record interface from
``TrackedRecordMixin``. It lives in its own module because ``tracking`` imports
``RecordDisplayMixin`` from ``base``, so ``base`` cannot import ``tracking`` at the top.

See ADR-0006 and ``docs/claude/record_system.md``.
"""

# Standard Library
from typing import Any

# 3rd Party
from pydatatracker import TrackedDict

# Project
from bastproxy.libs.records.tracking import TrackedRecordMixin, current_max_changes


class BaseDictRecord(TrackedRecordMixin, TrackedDict):
    """Base class for dictionary-based records, tracked by pydatatracker.

    Every mutation is logged as a change entry, and a locked record raises
    ``RuntimeError`` on every mutation. Record values stored in it are not linked as
    pydatatracker children: a record has its own parents and lock, and linking would
    unlock a locked record or lock a writable one.
    """

    def __init__(
        self,
        owner_id: str = "",
        data: dict[Any, Any] | None = None,
        track_record: bool = True,
    ) -> None:
        """Initialize the class.

        Args:
            owner_id: The owner id, per class by default.
            data: The initial content.
            track_record: Accepted and ignored. Dict records are never executed.

        Raises:
            TypeError: If data is not a dict.

        """
        if data:
            if not isinstance(data, dict):
                msg = f"data must be a dict not {type(data)}"
                raise TypeError(msg)
        else:
            data = {}
        TrackedDict.__init__(
            self,
            data,
            tracking_max_changes=current_max_changes(),
            tracking_capture_stack=False,
        )
        self._init_record(owner_id)
        self.original_data = dict(data)

    def _tracking_link_stored_value(self, value: Any, location: Any) -> None:
        """Link a stored value as a child, except a record.

        A record keeps its own parents and lock. Linking it would merge its lock with
        this dict's, so it is stored without a link.
        """
        if isinstance(value, TrackedRecordMixin):
            return
        super()._tracking_link_stored_value(value, location)

    @property
    def locked(self) -> bool:
        """Whether the record refuses changes."""
        return bool(self._tracking_locked)

    def _monitored_fields(self) -> list[str]:
        """A dict record has no monitored fields."""
        return []

    def _original_value(self, name: str) -> Any:
        """A dict record has no monitored fields, so there is no original value."""
        return None

    def one_line_summary(self) -> str:
        """Get a one line summary of the record."""
        first = str(next(iter(self.original_data.values()), "")).strip()
        return f"{self.__class__.__name__:<20} {self.uuid} {first}"

    def get_attributes_to_format(self) -> dict[int, list[tuple[str, Any]]]:
        """Get the attributes to include when formatting this dict record.

        Returns:
            Dictionary mapping section numbers to attribute lists.

        """
        attributes = super().get_attributes_to_format()
        attributes[2].append(("Data", dict(self)))
        if self.original_data != dict(self):
            attributes[2].append(("Original Data", self.original_data))

        return attributes  # type: ignore[no-any-return]
