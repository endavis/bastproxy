# Project: bastproxy
# Filename: plugins/core/async/_async.py
#
# File Description: a plugin to inspect async internals
#
# By: Bast
"""Module for tracking and managing records in an asynchronous environment.

This module provides functionality to inspect and manage asynchronous internals
through the `TrackedRecord` class, which allows for tracking changes to attributes
and managing relationships between records. It includes methods for logging updates,
comparing records, and handling event stacks, making it a valuable tool for
monitoring asynchronous operations.

Classes:
    TrackedRecord: A class that represents a record that can be tracked for changes,
                   inheriting from TrackedAttr.

Functions:
    is_record(obj: object) -> str:
        Determine if the given object is a trackable record.
"""

# Standard Library
import datetime
import logging
import traceback

from pydatatracker import TrackedAttr, add_to_ignore_in_stack

# 3rd Party
# Project
from bastproxy.libs.api import API

_record_types = []

add_to_ignore_in_stack(
    [
        "libs/records/",
        "libs/data",
        "libs/process",
        "libs/tracking",
        "plugins/test/newmon/utils",
        "plugins/test/newmon/types",
    ]
)


def is_record(obj: object) -> str:
    """Determine if the given object is a trackable record.

    This function checks if the provided object is an instance of `TrackedRecord`.
    If it is, the function further checks against a list of record types to determine
    the specific type of trackable object. If the object is not a trackable record,
    the function returns False.

    Args:
        obj: The object to check for trackability.

    Returns:
        str or bool: The type of trackable object if the object is a `TrackedRecord`,
                    otherwise False.

    """
    if isinstance(obj, TrackedRecord):
        return next(
            (item for item in _record_types if isinstance(obj, eval(item))),
            "TrackedRecord",
        )
    return ""


class TrackedRecord(TrackedAttr):
    """Represents a record that can be tracked for changes, inheriting from TrackedAttr.

    The `TrackedRecord` class is designed to encapsulate data that can be monitored
    for modifications. It provides mechanisms to track changes to its attributes,
    manage parent-child relationships with other tracked records, and log execution
    details.

    Attributes:
        owner_id (str): Unique identifier for the owner of the record.
        api (API): API instance for interacting with external systems.
        created_time (datetime): Timestamp when the record was created.
        execute_time_taken (float): Time taken for execution, initialized to -1.
        track_execution (bool): Flag indicating whether to track execution time.
        column_width (int): Width for formatting output.
        tracked_list (list): List of tracked items.
        tracked_attr (str): A string representing a tracked attribute.
        tracked_dict (dict): Dictionary for tracking key-value pairs.
        stack_at_creation (list): Stack trace at the time of record creation.
        event_stack (list): Stack of events associated with the record.
        executing (bool): Flag indicating if the record is currently executing.

    Methods:
        __init__(owner_id: str, track_execution: bool, parent: Optional[TrackedRecord]):
            Initializes a new instance of the TrackedRecord class.

        add_parent(parent: TrackedRecord, reset: bool = False):
            Adds a parent to this record, managing the parent-child relationship.

        __hash__() -> int:
            Returns a hash of the record based on its tracking UUID.

        __eq__(other: object) -> bool:
            Compares two TrackedRecord instances for equality based on their UUIDs.

        __repr__() -> str:
            Returns a string representation of the TrackedRecord instance.

        __lt__(value: object) -> bool:
            Compares two TrackedRecord instances based on their creation time.

        _tracking_onchange(change_log_entry):
            Tracks changes to attributes and their tracked children, adding the event
            stack to the change log entry.

        print_tracked_updates():
            Logs the tracked updates to the console.

        one_line_summary() -> str:
            Returns a one-line summary of the record, including
            execution time if applicable.

        fix_stack(stack: list) -> list:
            Converts the stack trace into a list of non-empty lines.

    """

    def __init__(self, owner_id: str = "", track_execution=True, parent=None) -> None:
        """Initialize a new instance of the TrackedRecord class.

        This constructor sets up the instance by generating a unique owner ID,
        initializing the API for external interactions, and setting up tracking
        mechanisms for changes to the record's attributes. It also captures the
        stack trace at the time of creation and initializes various attributes
        related to the record's state.

        Args:
            owner_id (str, optional): A unique identifier for the owner of the record.
                                    If not provided, a default value based on the
                                    class name and tracking UUID will be used.
            track_execution (bool, optional): A flag indicating whether to track
                                            execution time. Defaults to True.
            parent (Optional[TrackedRecord], optional): An optional parent record
                                                        to establish a parent-child
                                                        relationship. Defaults to None.

        Attributes:
            owner_id (str): The unique identifier for the owner of the record.
            api (API): The API instance for interacting with external systems.
            created_time (datetime): The timestamp when the record was created.
            execute_time_taken (float): Time taken for execution, initialized to -1.
            track_execution (bool): Flag indicating whether to track execution time.
            column_width (int): Width for formatting output.
            tracked_list (list): List of tracked items.
            tracked_attr (str): A string representing a tracked attribute.
            tracked_dict (dict): Dictionary for tracking key-value pairs.
            stack_at_creation (list): Stack trace at the time of record creation.
            event_stack (list): Stack of events associated with the record.
            executing (bool): Flag indicating if the record is currently executing.

        """
        # self.uuid = uuid4().hex
        TrackedAttr.__init__(self)
        if owner_id:
            self.owner_id = f"{owner_id}-{self._tracking_uuid}"
        else:
            self.owner_id = f"{self.__class__.__name__}-{self._tracking_uuid}"
        self.api = API(
            owner_id=self.owner_id or f"{self.__class__.__name__}:{self._tracking_uuid}"
        )
        self.tracking_add_observer(self._tracking_onchange)
        self._tracking_record_updates = []
        # create a unique id for this record
        # Add an API
        self.created_time = datetime.datetime.now(datetime.UTC)
        self.execute_time_taken = -1
        self.track_execution = track_execution
        # self._tracking_delimiter = '-'
        self.column_width = 15
        self.tracked_list = []
        self.tracked_attr = "some string"
        self.tracked_dict = {}
        stack = traceback.format_stack(limit=10)
        self.stack_at_creation = self.fix_stack(stack)
        if self.api("libs.api:has")("plugins.core.events:get.event.stack"):
            self.event_stack = self.api("plugins.core.events:get.event.stack")()
        else:
            self.event_stack = ["No event stack available"]

        self.executing = False
        # self.tracking_add_attribute_to_monitor('tracked_attr')
        # self.tracking_add_attribute_to_monitor('tracked_list')
        # self.tracking_add_attribute_to_monitor('tracked_dict')

    def add_parent(self, parent: "TrackedRecord", reset=False) -> None:
        """Add a parent to this record.

        This method establishes a parent-child relationship between this record
        and another `TrackedRecord`. If the `reset` flag is set to True,
        all existing parents will be removed before adding the new parent.

        Args:
            parent (TrackedRecord): The parent record to be added.
            reset (bool, optional): If True, removes all existing parents before
                                    adding the new parent. Defaults to False.

        """
        if reset:
            for existing_parent in self.parents:
                self.tracking_remove_observer(existing_parent._tracking_onchange)
            self.parents = []
        if parent not in self.parents:
            self.parents.append(parent)
        self.tracking_add_observer(parent._tracking_onchange)

    def __hash__(self) -> int:
        """Return a hash of the TrackedRecord instance.

        This method computes a hash value for the instance based on its
        tracking UUID and whether it is a record. This allows instances of
        `TrackedRecord` to be used in hash-based collections like sets and
        dictionaries.

        Returns:
            int: The hash value of the TrackedRecord instance.

        """
        return hash(f"{is_record(self)}:{self._tracking_uuid}")

    def __eq__(self, other) -> bool:
        """Compare two TrackedRecord instances for equality.

        This method checks if the UUIDs of two `TrackedRecord` instances are
        the same, indicating that they represent the same record. The comparison
        is only performed if the other object is also an instance of `TrackedRecord`.

        Args:
            other (object): The object to compare against.

        Returns:
            bool: True if the UUIDs are equal and both objects are instances of
                `TrackedRecord`; otherwise, False.

        """
        return (
            self._tracking_uuid == other._tracking_uuid
            if isinstance(other, TrackedRecord)
            else False
        )

    def __repr__(self) -> str:
        """Return a string representation of the TrackedRecord instance.

        This method provides a concise summary of the `TrackedRecord` instance,
        including its class name and tracking UUID. It is useful for debugging
        and logging purposes.

        Returns:
            str: A formatted string representing the TrackedRecord instance.

        """
        return f"{self.__class__.__name__}:{self._tracking_uuid}"

    def __lt__(self, value: object) -> bool:
        """Compare two TrackedRecord instances based on their creation time.

        This method determines if the current instance was created before another
        TrackedRecord instance by comparing their creation timestamps. It returns
        False if the other object does not have a creation time attribute.

        Args:
            value (object): The object to compare against.

        Returns:
            bool: True if the current instance was created before the other instance;
                otherwise, False.

        """
        return (
            self.created_time < value.created_time  # type: ignore
            if hasattr(value, "created_time")
            else False
        )

    def _tracking_onchange(self, change_log_entry) -> None:
        """Listen for changes to tracked children.

        This method updates the change log entry with the event stack if it is not
        already present. It interacts with the API to retrieve the current event stack
        when changes occur, ensuring that relevant context is captured in the change
        log.

        Args:
            change_log_entry: The log entry that records changes to attributes.

        Returns:
            None

        """
        if "event_stack" not in change_log_entry.extra and self.api("libs.api:has")(
            "plugins.core.events:get.event.stack"
        ):
            change_log_entry.extra["event_stack"] = self.api(
                "plugins.core.events:get.event.stack"
            )()

    def print_tracked_updates(self) -> None:
        """Log the tracked updates to the console.

        This method iterates through the list of tracked changes and logs each
        update using the logging module. It provides a way to monitor changes
        that have occurred in the tracked attributes.

        Args:
            None

        Returns:
            None

        """
        for item in self._tracking_changes:
            logging.info(item)

    def one_line_summary(self):
        """Generate a one-line summary of the record.

        This method returns a formatted string that summarizes the key attributes
        of the record, including the class name, tracking UUID, owner ID, and
        execution time if applicable. It provides a quick overview of the record's
        state for logging or display purposes.

        Args:
            None

        Returns:
            str: A formatted string summarizing the record's key attributes.

        """
        if self.execute_time_taken > 0:
            return (
                f"{self.__class__.__name__:<20} {self._tracking_uuid} "
                f"{self.owner_id} {self.execute_time_taken:.2f}ms"
            )
        return f"{self.__class__.__name__:<20} {self._tracking_uuid} {self.owner_id}"

    def fix_stack(self, stack) -> list[str]:
        """Process the stack trace to remove empty lines and return a cleaned list.

        This method takes a stack trace as input and returns a new list that
        contains only the non-empty lines from the original stack. It is useful
        for improving the readability of stack traces by filtering out unnecessary
        empty lines.

        Args:
            stack (list): The original stack trace, which may contain empty lines.

        Returns:
            list[str]: A list of non-empty lines extracted from the stack trace.

        """
        new_stack = []
        for line in stack:
            new_stack.extend([nline for nline in line.splitlines() if nline])
        return new_stack
