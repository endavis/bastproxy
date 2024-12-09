# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/utils/changelog.py
#
# File Description: Holds items for change tracking
#
# By: Bast
"""Module that holds a class for monitoring attributes and recording changes.

This module provides the ChangeLogEntry class, which is designed to track
changes to specific attributes, capturing relevant information such as the
time of change, the actor responsible, and the context of the change. It
includes methods for formatting and representing this information in a
structured manner.

Classes:
    ChangeLogEntry: A class that represents a change log entry, including
                    methods for tracking and formatting changes.

Functions:
    add_to_ignore_in_stack(list): Adds specified items to the ignore list
                                   for the call stack.
    fix_header(header_name): Converts a header name from snake_case to Title Case.
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
ignore_in_stack = []


def add_to_ignore_in_stack(tlist: list) -> None:
    """Add specified items to the ignore list for the call stack.

    This function takes a list of items and appends them to the global
    ignore_in_stack list, which is used to filter out specific entries
    from the call stack when identifying the relevant actor. This helps
    in managing which parts of the stack should be considered during
    change tracking.

    Args:
        tlist (list): A list of items to be added to the ignore list.

    Returns:
        None

    Raises:
        None

    """
    ignore_in_stack.extend(tlist)


def fix_header(header_name: str) -> str:
    """Convert a header name from snake_case to Title Case.

    This function takes a string formatted in snake_case and transforms it
    into a more readable format by replacing underscores with spaces and
    capitalizing the first letter of each word. It is useful for formatting
    headers in a user-friendly manner.

    Args:
        header_name (str): The header name in snake_case format.

    Returns:
        str: The formatted header name in Title Case.

    Raises:
        None

    """
    return header_name.replace("_", " ").title()


class ChangeLogEntry:
    """A class that monitors attributes and records changes to them.

    The ChangeLogEntry class is designed to track changes to specific attributes,
    capturing relevant information such as the time of change, the actor
    responsible, and the context of the change. It provides methods to format and
    represent this information in a structured manner.

    Attributes:
        uuid (str): A unique identifier for the change log entry.
        tracked_item_uuid (str): The UUID of the item being tracked.
        extra (dict): Additional information about the change.
        header_column_width (int): The width for formatting headers in output.
        created_time (datetime): The timestamp when the entry was created.
        stack (list): The call stack at the time of the change.
        actor (list): Information about the actor responsible for the change.
        tree (list): A hierarchical representation of related changes.

    Methods:
        find_relevant_actor(stack):
            Identifies the actor responsible for the change based on the call stack.

        get_stack():
            Retrieves the current call stack, excluding the last two lines.

        __repr__():
            Returns a string representation of the ChangeLogEntry.

        __eq__(value):
            Compares two ChangeLogEntry instances for equality based on their UUIDs.

        __lt__(value):
            Compares two ChangeLogEntry instances based on their creation time.

        copy(new_type, new_item_uuid):
            Creates a copy of the current ChangeLogEntry with a new type and UUID.

        format_detailed(show_stack=False, data_lines_to_show=10):
            Formats the change record for detailed output.

        format_data(name, data_lines_to_show):
            Formats specific data for output based on the provided name.

        add_to_tree(uuid):
            Adds a new entry to the change tree.

    """

    def __init__(self, item_uuid: str, **kwargs) -> None:
        """Initialize a new instance of the ChangeLogEntry class.

        This constructor sets up the instance by generating a unique UUID, storing
        the provided item UUID, and processing any additional keyword arguments. It
        also initializes various attributes related to the instance's state,
        including the creation time and relevant actor information.

        Args:
            item_uuid (str): The UUID of the item being tracked.
            **kwargs: Additional keyword arguments for extra information.

        Returns:
            None

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
        """Identify the actor responsible for the change based on the call stack.

        This method analyzes the provided stack trace to find the first relevant
        actor that is not in the ignore list. It returns the actor's information,
        which includes the file and function where the change occurred.

        Args:
            stack (list[str]): The call stack to analyze for identifying the actor.

        Returns:
            str: A string containing the file and function of the relevant actor,
                or an empty string if no actor is found.

        Raises:
            None

        """
        return next(
            (
                line.strip()
                for line in reversed(stack)
                if "File" in line
                and all(actor not in line for actor in ignore_in_stack)
            ),
            "",
        )

    def get_stack(self) -> list:
        """Retrieve the current call stack, excluding the last two lines.

        This method captures the stack trace at the point of invocation and formats it
        into a list of strings, omitting the last two lines which are typically not
        relevant to the change being logged.

        Returns:
            list: A list of strings representing the formatted call stack,
                excluding the last two lines.

        Raises:
            None

        """
        stack = traceback.format_stack()
        return [line for line in stack[:-2] if line.strip()]

    def __repr__(self) -> str:
        """Return a string representation of the ChangeLogEntry.

        This method provides a concise summary of the ChangeLogEntry instance,
        including the creation time, tracked item UUID, and any additional
        information stored in the extra attribute. It is useful for debugging
        and logging purposes.

        Returns:
            str: A formatted string representing the ChangeLogEntry instance.

        """
        return (
            f"ChangeLogEntry: {self.created_time} {self.tracked_item_uuid} {self.extra}"
        )

    def __eq__(self, value: object) -> bool:
        """Compare two ChangeLogEntry instances for equality.

        This method checks if the UUIDs of two ChangeLogEntry instances are the same,
        indicating that they represent the same change log entry. It ensures that the
        comparison is only performed between instances of ChangeLogEntry.

        Args:
            value (object): The object to compare against.

        Returns:
            bool: True if the UUIDs are equal and both objects are instances of
                ChangeLogEntry; otherwise, False.

        Raises:
            None

        """
        return self.uuid == value.uuid if isinstance(value, ChangeLogEntry) else False

    def __lt__(self, value: object) -> bool:
        """Compare two ChangeLogEntry instances based on their creation time.

        This method determines if the current ChangeLogEntry was created before
        another instance by comparing their creation timestamps. It ensures that
        the comparison is only performed if the other object has a creation time.

        Args:
            value (object): The object to compare against.

        Returns:
            bool: True if the current instance was created before the other instance;
                otherwise, False.

        Raises:
            None

        """
        return (
            self.created_time < value.created_time  # type: ignore
            if hasattr(value, "created_time")
            else False
        )

    def copy(self, new_type: str, new_item_uuid: str) -> "ChangeLogEntry":
        """Create a copy of the current ChangeLogEntry with a new type and UUID.

        This method allows for the duplication of a ChangeLogEntry while modifying
        its type and UUID. The new entry retains the original's attributes, such as
        the creation time, stack trace, actor information, and change tree.

        Args:
            new_type (str): The new type to assign to the copied entry.
            new_item_uuid (str): The UUID for the new copied entry.

        Returns:
            ChangeLogEntry: A new instance of ChangeLogEntry with the updated type
                            and UUID, preserving other attributes from the original.

        Raises:
            None

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
        """Format the change record for detailed output.

        This method generates a structured representation of the ChangeLogEntry,
        including relevant attributes such as creation time, type, actor, and
        additional information. It can also display the call stack if requested.

        Args:
            show_stack (bool, optional): Indicates whether to include the call stack
                                        in the output. Defaults to False.
            data_lines_to_show (int, optional): The maximum number of lines to show
                                                for data attributes. Defaults to 10.

        Returns:
            list: A list of formatted strings representing the detailed change record.

        Raises:
            None

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
        """Format specific data for output based on the provided name.

        This method retrieves the value associated with the given attribute name
        and formats it for display. It handles various data types and ensures that
        the output is structured and readable, including options for limiting the
        number of lines shown.

        Args:
            name (str): The name of the attribute or key to format.
            data_lines_to_show (int): The maximum number of lines to display for
                                    the formatted data.

        Returns:
            list: A list of formatted strings representing the specified data.

        Raises:
            None

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

    def add_to_tree(self, uuid: str) -> None:
        """Add a new entry to the change tree.

        This method inserts the specified UUID at the beginning of the tree list,
        allowing for the tracking of related changes in a hierarchical manner.
        It helps maintain the order of changes as they are recorded.

        Args:
            uuid (str): The UUID of the change entry to add to the tree.

        Returns:
            None

        Raises:
            None

        """
        self.tree.insert(0, uuid)
