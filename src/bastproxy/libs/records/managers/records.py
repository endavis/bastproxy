# Project: bastproxy
# Filename: libs/records/managers/records.py
#
# File Description: a manager that handles records of all types
#
# By: Bast
"""This module holds a manager that handles records of all types."""

import contextlib

# Standard Library
from typing import TYPE_CHECKING

# 3rd Party
# Project
from bastproxy.libs.api import API as BASEAPI
from bastproxy.libs.queue import SimpleQueue
from bastproxy.libs.stack import SimpleStack

if TYPE_CHECKING:
    pass


class RecordManager:
    """Manager for tracking and storing records of various types.

    This class manages a collection of records, maintains an active record
    stack, and provides functionality for filtering and querying records.

    """

    def __init__(self):
        """Keep the last max_records of each type.

        track the active record.
        """
        self.max_records: int = 5000
        self.records: dict[str, SimpleQueue] = {}
        self.api = BASEAPI(owner_id=__name__)
        self.record_instances = {}
        self.active_record_stack = SimpleStack()
        # don't show these records in detailed output
        self.default_filter = ["LogRecord"]

    def start(self, record):
        """Start tracking a new active record by pushing it onto the stack.

        Args:
            record: The record to mark as active.

        """
        self.active_record_stack.push(record)

    def end(self, record):
        """End tracking an active record by removing it from the stack.

        Args:
            record: The record to remove from the active stack.

        """
        if record != self.active_record_stack.peek():
            from bastproxy.libs.records import LogRecord

            LogRecord(
                f"RecordManger end: Record {record} is not the same as the active record {self.active_record_stack.peek()}",
                level="warning",
            )
            self.active_record_stack.remove(record)
        else:
            self.active_record_stack.pop()

    def get_latest_record(self):
        """Get the currently active record from the top of the stack.

        Returns:
            The most recently started record, or None if stack is empty.

        """
        return self.active_record_stack.peek()

    def get_children(self, record, record_filter=None):
        """Get all direct children of a record.

        Args:
            record: The parent record to find children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A list of child records.

        """
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        return list(
            {
                rec
                for rec in self.record_instances.values()
                for parent in rec.parents
                if parent.uuid == record.uuid and rec.__class__.__name__ not in rfilter
            }
        )

    def get_all_children_dict(self, record, record_filter=None):
        """Get all children recursively as a nested dictionary.

        Args:
            record: The parent record to find children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A nested dictionary of records and their children.

        """
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_children(record, record_filter)
        children.sort()
        return {
            child: self.get_all_children_dict(child, rfilter)
            for child in children
            if child.__class__.__name__ not in rfilter
        }

    def get_all_children_list(self, record, record_filter=None):
        """Get all children recursively as a flat list.

        Args:
            record: The parent record to find children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A flat list of all descendant records.

        """
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_all_children_dict(record, record_filter)
        return self.api("plugins.core.utils:get.keys.from.dict")(children)

    def format_all_children(self, record, record_filter=None):
        """Format all children as a tree structure with indentation.

        Args:
            record: The parent record to format children for.
            record_filter: Optional list of record types to exclude.

        Returns:
            A list of formatted strings showing the record tree.

        """
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        children = self.get_all_children_dict(record, rfilter)
        return [
            f"{'       ' * 0}{record.one_line_summary()}",
            *self.format_all_children_helper(children, record_filter=rfilter),
        ]

    def format_all_children_helper(
        self, children, indent=0, emptybar=None, output=None, record_filter=None
    ):
        """Helper method to recursively format children with proper indentation.

        Args:
            children: Dictionary of child records to format.
            indent: Current indentation level (default: 0).
            emptybar: Dictionary tracking which indent levels are empty.
            output: List to append formatted lines to.
            record_filter: Optional list of record types to exclude.

        Returns:
            A list of formatted strings with proper tree indentation.

        """
        if not emptybar:
            emptybar = {}
        emptybar[indent] = False
        if not record_filter:
            record_filter = []
        rfilter = self.default_filter[:]
        rfilter.extend(record_filter)
        output = output or []
        all_children = list(children.keys())
        pre_string = "".join("    " if emptybar[i] else " |  " for i in range(indent))
        for child in children:
            all_children.pop(all_children.index(child))
            output.append(f"{pre_string} |-> {child.one_line_summary()}")
            if not all_children:
                emptybar[indent] = True
            self.format_all_children_helper(
                children[child], indent + 1, emptybar, output, rfilter
            )
        return output

    def add(self, record):
        """Add a record to the manager's tracking system.

        Args:
            record: The record to add.

        """
        queuename = record.__class__.__name__
        if queuename not in self.records:
            self.records[queuename] = SimpleQueue(self.max_records)
        if record.uuid in self.record_instances:
            from bastproxy.libs.records import LogRecord

            LogRecord(
                f"Record UUID collision {record.uuid} already exists in the record manager",
                level="error",
            )()
        self.records[queuename].enqueue(record)
        self.record_instances[record.uuid] = record

        if last_record := self.records[queuename].last_automatically_removed_item:
            with contextlib.suppress(KeyError):
                del self.record_instances[last_record.uuid]

    def get_types(self):
        """Get all record types and their counts.

        Returns:
            A list of tuples containing (record_type, count).

        """
        return [(key, self.records[key].size()) for key in self.records]

    def get_records(self, recordtype, count=10):
        """Get the last N records of a specific type.

        Args:
            recordtype: The type of records to retrieve.
            count: Number of records to retrieve (default: 10).

        Returns:
            A list of records, or None if type doesn't exist.

        """
        records = self.records.get(recordtype, None)
        return records.get_last_x(count) if records else records

    def get_record(self, recordid):
        """Get a specific record by its UUID.

        Args:
            recordid: The UUID of the record to retrieve.

        Returns:
            The record if found, None otherwise.

        """
        return self.record_instances.get(recordid, None)


RMANAGER = RecordManager()
