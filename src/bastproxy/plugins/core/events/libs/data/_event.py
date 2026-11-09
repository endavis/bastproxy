# Project: bastproxy
# Filename: libs/records/rtypes/eventargs.py
#
# File Description: Holds the record type for event arguments
#
# By: Bast
"""
Holds the log record type
"""

# Standard Library
from typing import Any

# 3rd Party
# Project
from bastproxy.libs.records.rtypes.dictrecord import BaseDictRecord


class EventDataRecord(BaseDictRecord):
    def __init__(self, owner_id: str = "", event_name: str = "unknown", data: dict | None = None):
        """
        initialize the class
        """
        self.event_name = event_name
        self._received = False
        BaseDictRecord.__init__(self, owner_id, data)

    def add_receiving_event(self, raised: Any) -> None:
        """Record that an event received this data.

        The first event becomes ``parent`` and replaces the creating record in
        ``parents``. Each later event, for a record raised again, is added to
        ``parents`` and ``parent`` stays the first one.

        Args:
            raised: The ``ProcessRaisedEvent`` that received this record.

        """
        if not self._received:
            self._received = True
            self.parent = raised
            self.parents = [raised]
        else:
            self.add_parent(raised)

    def one_line_summary(self):
        """
        get a one line summary of the record
        """
        return f"{self.__class__.__name__:<20} {self.uuid} {self.event_name}"

    def get_attributes_to_format(self):
        attributes = super().get_attributes_to_format()
        attributes[0].append(("Event Name", "event_name"))
        return attributes
