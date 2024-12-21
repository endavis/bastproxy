# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/utils/changelog.py
#
# File Description: Holds items for change tracking
#
# Docstrings last checked and updated: 12/19/2024
#
# By: Bast
r"""Change logging functionality for tracking modifications in data structures.

This module provides utilities for tracking and logging changes in data structures,
with a focus on maintaining detailed records of modifications, their origins, and
their relationships.

Key Components:
    - ChangeLogEntry: Core class for recording individual changes
    - Stack trace management for identifying change origins
    - Hierarchical change tracking with parent-child relationships
    - Detailed formatting utilities for change visualization

Features:
    - Unique identifiers for each change entry
    - Timestamp tracking for change sequencing
    - Actor identification from call stack
    - Hierarchical change relationships
    - Detailed and summary change formatting
    - Stack trace filtering
    - Custom data formatting

Functions:
    add_to_ignore_in_stack: Add items to stack trace filter
    fix_header: Convert snake_case to Title Case for display

Classes:
    ChangeLogEntry: Main class for tracking individual changes

"""
# Standard Library
import datetime
import traceback
import pprint
import ast
from uuid import uuid4

# 3rd Party

# Project

# Globals
_IGNORE_IN_STACK = []


def add_to_ignore_in_stack(tlist: list[str]) -> None:
    """Add entries to the list of items to ignore when processing stack traces.

    Extends the global _IGNORE_IN_STACK list with new entries that should be filtered
    out when analyzing call stacks for change tracking purposes.

    Args:
        tlist: List of strings to add to the ignore list. Each string represents a
            pattern that will be excluded from stack trace analysis.
            Note: this is not a regex pattern, the string will be used as is

    """
    _IGNORE_IN_STACK.extend(tlist)


def fix_header(header_name: str) -> str:
    """Convert a header name from snake_case to Title Case format.

    Takes a string in snake_case format and converts it to Title Case by replacing
    underscores with spaces and capitalizing each word.

    Args:
        header_name: String to convert from snake_case to Title Case

    Returns:
        The formatted string in Title Case with spaces instead of underscores

    """
    return header_name.replace("_", " ").title()


class ChangeLogEntry:
    """Represents an entry in the change log for tracking modifications.

    This class is used to create and manage a change log entry, which
    records detailed information about modifications to data structures. Each
    entry includes metadata such as timestamps, stack traces, and actor
    identification, and supports hierarchical relationships between changes.

    """

    def __init__(self, item_uuid: str, **kwargs) -> None:
        """Initialize a new ChangeLogEntry instance.

        Creates a new change log entry with a unique identifier and metadata. Sets up
        tracking information including timestamps, stack traces, and actor
        identification.

        Args:
            item_uuid: Identifier for the item being tracked
            **kwargs: Additional metadata to store about the change.
                Common keys include:
                    - type: The type of change (e.g., "update", "add", "remove")
                    - value: The new value associated with the change
                    - location: Where in the data structure the change occurred
                    - action: The action that triggered the change
                    - method: The method name that caused the change

        """
        self.uuid = uuid4().hex
        self.tracked_item_uuid = item_uuid
        self.extra = kwargs
        self.header_column_width = 17
        self.created_time = datetime.datetime.now(datetime.timezone.utc)
        self.stack = self.get_stack()
        self.actor = self.find_relevant_actor(self.stack)
        self.tree = []
        for item in self.extra:
            if item == "location":
                continue
            if not isinstance(self.extra[item], str):
                self.extra[item] = repr(self.extra[item])

    def find_relevant_actor(self, stack: list[str]) -> str:
        """Find the most relevant actor from the stack trace that caused the change.

        Searches through the stack trace in reverse order to find the first line
        containing 'File' that isn't in the ignore list. This helps identify where the
        change originated from.

        Args:
            stack: List of stack trace strings to search through

        Returns:
            The first relevant stack trace line found, or empty string if none found

        """
        return next(
            (
                line.strip()
                for line in reversed(stack)
                if "File" in line
                and all(actor not in line for actor in _IGNORE_IN_STACK)
            ),
            "",
        )

    def get_stack(self) -> list[str]:
        """Retrieve the current stack trace, excluding the last two entries.

        This method captures the current stack trace and filters out the last two
        entries, which typically correspond to the call to this method and its
        immediate caller. The resulting stack trace is used for tracking the origin
        of changes.

        Returns:
            A list of strings representing the filtered stack trace.

        """
        stack = traceback.format_stack()
        return [line for line in stack[:-2] if line.strip()]

    def __repr__(self) -> str:
        """Return a string representation of the ChangeLogEntry.

        This method provides a concise summary of the ChangeLogEntry instance, including
        the creation time, tracked item UUID, and any additional information stored in
        the extra attribute. It is useful for debugging and logging purposes.

        Returns:
            A formatted string representing the ChangeLogEntry instance

        """
        return (
            f"ChangeLogEntry: {self.created_time} {self.tracked_item_uuid} {self.extra}"
        )

    def __eq__(self, value: object) -> bool:
        """Compare this ChangeLogEntry with another for equality.

        Determines if two ChangeLogEntry instances are equal by comparing their UUIDs.
        Returns False if the other object is not a ChangeLogEntry instance.

        Args:
            value: The object to compare with this ChangeLogEntry

        Returns:
            True if both objects are ChangeLogEntries with the same UUID, False
            otherwise

        """
        return self.uuid == value.uuid if isinstance(value, ChangeLogEntry) else False

    def __lt__(self, value: object) -> bool:
        """Compare if this ChangeLogEntry is less than another by creation time.

        Compares the created_time attributes of two entries. Returns False if the other
        object doesn't have a created_time attribute.

        Args:
            value: The object to compare with this ChangeLogEntry

        Returns:
            True if this entry was created earlier than the other, False otherwise

        """
        return (
            self.created_time < value.created_time  # type: ignore
            if hasattr(value, "created_time")
            else False
        )

    def copy(self, new_type: str, new_item_uuid: str) -> "ChangeLogEntry":
        """Create a copy of this ChangeLogEntry with a new type and UUID.

        Creates a new ChangeLogEntry instance with copied metadata but different type
        and UUID. Maintains the original timestamps, stack traces, and tree structure.

        Args:
            new_type: The type to assign to the new entry
            new_item_uuid: The UUID to assign to the new entry

        Returns:
            A new ChangeLogEntry instance with copied data and new identifiers

        """
        extra = self.extra.copy()
        extra["type"] = new_type
        new_log = ChangeLogEntry(new_item_uuid, **extra)
        new_log.created_time = self.created_time
        new_log.stack = self.stack
        new_log.actor = self.actor
        new_log.tree = self.tree
        return new_log

    def format_detailed(
        self, show_stack: bool = False, data_lines_to_show: int = 10
    ) -> list[str]:
        r"""Generate a detailed formatted representation of the change entry.

        Creates a list of formatted strings containing all relevant information about
        the change, including UUIDs, timestamps, values, and optionally stack traces.

        Args:
            show_stack: Whether to include stack trace in output
            data_lines_to_show: Maximum number of lines to show for each data field

        Returns:
            List of formatted strings representing the change entry details

        """
        item_order = [
            "created_time",
            "type",
            "actor",
            "location",
            "action",
            "sub_command",
            "method",
            "passed_index",
            "locked",
            "value",
            "data_pre_change",
            "data_post_change",
            "removed_items",
        ]

        tmsg = [
            f"{'Change UUID':<{self.header_column_width}} : {self.uuid}",
            f"{'Object UUID':<{self.header_column_width}} : {self.tracked_item_uuid}",
        ]

        for item in item_order:
            tmsg.extend(self.format_data(item, data_lines_to_show))

        if self.tree:
            item = self.tree[0]
            tmsg.append(
                f"{'Tree':<{self.header_column_width}} : {item['type']}({item['uuid']})"
                f"{' ' + item['location'] if 'location' in item else ''}"
            )
            indent = 2
            for item in self.tree[1:]:
                tmsg.append(
                    f"{'':<{self.header_column_width}} : {' ' * indent}|-> "
                    f"{item['type']}({item['uuid']})"
                    f"{' ' + item['location'] if 'location' in item else ''}"
                )
                indent += 4

        if self.extra:
            for item in self.extra:
                if item in item_order or item == "tree":
                    continue

                tmsg.extend(self.format_data(item, data_lines_to_show))

        if show_stack and self.stack:
            tmsg.append(f"{'Stack':<{self.header_column_width}} :")
            tmsg.extend(
                [
                    f"{'':<{self.header_column_width}} {line}"
                    for line in self.stack[-40:]
                    if line.strip()
                ]
            )

        return tmsg

    def format_data(self, name: str, data_lines_to_show: int) -> list[str]:
        """Format the data for a given attribute or extra metadata.

        Retrieves the value of the specified attribute or extra metadata, formats it
        for display, and returns a list of formatted strings. Handles multi-line data
        and limits the number of lines shown.

        Args:
            name: The name of the attribute or extra metadata to format.
            data_lines_to_show: Maximum number of lines to show for each data field.

        Returns:
            A list of formatted strings representing the data.

        """
        data = getattr(self, name, self.extra.get(name, "-#@$%##$"))

        if data == "-#@$%##$":
            return []

        header = fix_header(name)
        try:
            testdata = ast.literal_eval(data)
        except Exception:
            testdata = data

        if testdata in [None, "None", ""]:
            return []

        testdata_string = pprint.pformat(testdata, width=80).splitlines()

        if len(testdata_string) == 1:
            return [f"{header:<{self.header_column_width}} : {testdata}"]

        tmsg = [f"{header:<{self.header_column_width}} : {testdata_string[0]}"]
        tmsg.extend(
            f"{'':<{self.header_column_width}} : {line}"
            for line in testdata_string[1:data_lines_to_show]
        )
        if len(testdata_string) > data_lines_to_show:
            tmsg.append(f"{'':<{self.header_column_width}} : ...")
        return tmsg

    def add_to_tree(self, info: dict[str, str]) -> None:
        """Add a new entry to the change tree.

        This method inserts a dictionary containing information about a change at
        the beginning of the tree structure. It allows for the organization of
        changes in a hierarchical manner, facilitating easy tracking of related
        changes.

        Args:
            info: A dictionary containing information about the
                change to be added to the tree.

        Returns:
            None

        """
        self.tree.insert(0, info)
