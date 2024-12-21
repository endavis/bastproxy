# -*- coding: utf-8 -*-
# Project: bastproxy
# Filename: libs/tracking/types/_trackbase.py
#
# File Description: Holds the TrackBase class for tracking changes to objects.
#
# Docstrings last checked and updated: 12/19/2024
#
# By: Bast
"""Module for monitoring and managing data with tracking capabilities.

This module provides the `TrackBase` class, which allows for the tracking
of changes to opjects and the management of relationships between tracked
objects and their children. It includes methods for locking and unlocking
objects, notifying observers of changes, and maintaining a history of
original values, making it a valuable tool for monitoring state changes in
an application.

Key Components:
    - TrackBase: A class that provides a framework for tracking and managing
      changes to objects.
    - Methods for adding, locking, unlocking, and notifying changes to objects.
    - Utility methods for handling object changes, conversions, and tracking.

Features:
    - Automatic conversion of tracked values.
    - Management of parent-child relationships for tracked objects.
    - Notification system for observers when object changes occur.
    - Locking mechanism to prevent modifications to objects.
    - Comprehensive logging of object changes and original values.

Usage:
    - Instantiate TrackBase to create an object that tracks changes.
    - Use `tracking_add_observer` to add an observer to monitor changes.
    - Lock and unlock the object using `lock` and `unlock` methods.
    - Access original values and change logs through provided methods.
    - when modifying an object, create a change log entry using
        `tracking_create_change` to record the change.

Classes:
    - `TrackBase`: Represents a class that can track object changes.

"""
# Standard Library
from typing import Any, Callable, Literal
from uuid import uuid4
from functools import wraps
import datetime
import logging

# 3rd Party

# Project
from ..utils.changelog import ChangeLogEntry


def check_lock(method: Callable[..., Any]) -> Callable[..., Any]:
    """Ensure methods are not called on locked objects.

    This decorator wraps a method to check if the instance is locked before
    executing the method. If the instance is locked, it raises a RuntimeError,
    preventing any modifications to the object.

    Args:
        method: The method to be decorated for lock checking.

    Returns:
        The wrapped method that includes lock checking functionality.

    """

    @wraps(method)
    def wrapper(self, *args, **kwargs) -> Any:
        """Check if the instance is locked before executing the method.

        This function is used as a decorator to ensure that a method cannot be called
        if the instance is in a locked state. If the instance is locked, it raises a
        RuntimeError, preventing any modifications to the object.

        Args:
            self: The instance of the class.
            *args: Positional arguments to be passed to the method.
            **kwargs: Keyword arguments to be passed to the method.

        Returns:
            The result of the method if the instance is not locked.

        """
        if hasattr(self, "_tracking_locked") and self._tracking_locked:
            raise RuntimeError(
                f"{self.__class__.__name__} is locked and cannot be modified."
            )
        return method(self, *args, **kwargs)

    return wrapper


def track_changes(method: Callable[..., Any]) -> Callable[..., Any]:
    """Track changes made to an object.

    This decorator wraps a method to monitor changes to the object.
    It resets the tracking context, captures the state before and after
    the method execution, and logs any changes, including removed items and
    updates to tracked objects.

    Args:
        method: The method to be decorated for change tracking.

    Returns:
        The wrapped method that includes change tracking functionality.

    """

    @wraps(method)
    def wrapper(self, *args, **kwargs) -> Any:
        """Track changes to the object before and after method execution.

        This function is used as a decorator to monitor changes made to the object
        by capturing its state before and after the method execution. It logs any
        changes, including removed items and updates to tracked objects, ensuring
        that all modifications are recorded and can be retrieved later.

        Args:
            self: The instance of the class.
            *args: Positional arguments to be passed to the method.
            **kwargs: Keyword arguments to be passed to the method.

        Returns:
            The result of the method execution.

        """
        # reset the tracking context
        if self._tracking_is_trackable(self) in ["TrackedDict", "TrackedList"]:
            data_pre_change = repr(self)

        self._tracking_context = {}

        # Call the original method
        result = method(self, *args, **kwargs)

        # Check if the object has a tracking_context attribute (for tracking changes)
        if self._tracking_context and "action" in self._tracking_context:

            if "removed_items" in self._tracking_context:
                for olditem in self._tracking_context["removed_items"]:
                    if self._tracking_is_trackable(olditem):
                        if olditem._tracking_uuid in self._tracking_child_tracked_items:
                            del self._tracking_child_tracked_items[
                                olditem._tracking_uuid
                            ]
                        olditem.tracking_remove_observer(
                            self._tracking_notify_observers
                        )

            if self._tracking_is_trackable(self) in ["TrackedDict", "TrackedList"]:
                self._tracking_context["data_pre_change"] = data_pre_change
                self._tracking_context["data_post_change"] = repr(self)
            self._tracking_context["method"] = method.__name__
            self.tracking_create_change(**self._tracking_context)

        self._tracking_context = {}

        return result

    return wrapper


class TrackBase:
    """Base class for tracking changes to objects.

    This class provides a framework for tracking and managing changes to objects.
    It includes methods for adding observers, locking and unlocking objects,
    notifying observers of changes, and maintaining a history of changes. It
    supports automatic conversion of values to trackable types and management of
    parent-child relationships for tracked objects.

    """

    def __init__(
        self,
        tracking_name: str | None = None,
        tracking_auto_converted_in: str | None = None,
        tracking_auto_convert: bool = False,
        tracking_parent: "TrackBase | None" = None,
        tracking_location: str | None = "",
        tracking_delimiter: str = "+",
        **kwargs: dict,
    ) -> None:
        """Initialize a new instance of the TrackBase class.

        This constructor sets up the instance by initializing various attributes
        related to tracking, including the tracking name, UUID, observers, and
        context. It also establishes relationships with parent tracked items and
        prepares the instance for monitoring changes.

        Args:
            tracking_name: The name used for tracking the instance.
            tracking_auto_converted_in: The context in which automatic conversion
                occurs.
            tracking_auto_convert: Flag indicating whether to automatically convert
                values.
            tracking_parent: An optional parent instance for establishing a hierarchy.
            tracking_location: The location of the tracked attribute.
            tracking_delimiter: The delimiter used for tracking attribute locations.
            **kwargs: Additional keyword arguments for further customization.

        Returns:
            None

        """
        self._tracking_name = tracking_name
        self._tracking_auto_converted_in = tracking_auto_converted_in
        self._tracking_uuid = uuid4().hex
        self._tracking_observers = {}
        self._tracking_context = {}
        self._tracking_changes: list[ChangeLogEntry] = []
        self._tracking_locked = False
        self._tracking_auto_convert = tracking_auto_convert
        self._tracking_created = datetime.datetime.now()
        self._tracking_child_tracked_items = {}
        self._tracking_delimiter = tracking_delimiter
        self._tracking_debug_flag = False
        if tracking_parent:
            tracking_parent._tracking_add_child_tracked_item(tracking_location, self)

        self.tracking_create_change(action="init", init_data=f"{self}")
        self._tracking_convert_all_values()

    def _tracking_convert_value(self, value: Any, location: Any = "") -> Any:
        """Convert a value to a trackable type if automatic conversion is enabled.

        This method checks if automatic conversion is enabled for the instance and,
        if so, converts the provided value into a trackable type. It ensures that
        the value is appropriately formatted for tracking purposes, allowing for
        consistent monitoring of changes.

        Args:
            value: The value to be converted to a trackable type.
            location: An optional string indicating the location of the value.

        Returns:
            The converted trackable value, or the original value if no conversion
                is performed.

        """
        if hasattr(self, "_tracking_auto_convert") and self._tracking_auto_convert:
            value = self._tracking_convert_to_trackable(
                value,
                tracking_auto_converted_in=self._tracking_uuid,
                tracking_auto_convert=self._tracking_auto_convert,
                tracking_parent=self,
                tracking_location=location,
            )
        return value

    def _tracking_debug(self, message: str) -> None:
        """Log a debug message if debugging is enabled.

        This method checks if the debugging flag is set for the instance. If debugging
        is enabled, it logs the provided message using the logging module, including
        a shortened version of the instance's UUID for identification.

        Args:
            message: The debug message to be logged.

        Returns:
            None

        """
        if self._tracking_debug_flag:
            logging.info(
                f"{self._tracking_uuid[:4]}..{self._tracking_uuid[-4:]} - {message}"
            )

    def _tracking_add_child_tracked_item(
        self, location: str | None, trackable_item: "TrackBase"
    ) -> None:
        """Add a child tracked item to the current instance.

        This method registers a specified child tracked item within the tracking
        structure, allowing it to be monitored for changes. It also ensures that
        the child item inherits the lock state of the parent and adds the parent
        as an observer to the child item.

        Args:
            location: The location of the child item within the tracking structure.
            trackable_item: The child item to be added to the tracking structure.

        Returns:
            None

        """
        self._tracking_child_tracked_items[trackable_item._tracking_uuid] = {
            "location": location,
            "item": trackable_item,
        }
        if self._tracking_locked:
            trackable_item.lock()
        else:
            trackable_item.unlock()
        trackable_item.tracking_add_observer(self._tracking_notify_observers)

    def _tracking_remove_child_tracked_item(self, trackable_item: "TrackBase") -> None:
        """Remove a child tracked item from the current instance.

        This method unregisters a specified child tracked item from the tracking
        structure, ensuring that it is no longer monitored for changes. It also
        removes the parent as an observer from the child item, breaking the
        relationship between the parent and child in the tracking system.

        Args:
            trackable_item: The child item to be removed from the tracking structure.

        Returns:
            None

        """
        self._tracking_child_tracked_items.pop(trackable_item._tracking_uuid, None)
        trackable_item.tracking_remove_observer(self._tracking_notify_observers)

    def _tracking_convert_all_values(self) -> None:
        """Convert all values of the instance to trackable types.

        This method iterates through all attributes of the instance and converts
        them to trackable types if automatic conversion is enabled. It ensures that
        all values are appropriately formatted for tracking purposes, allowing for
        consistent monitoring of changes. This method should be overridden in any
        subclass.

        Args:
            None

        Returns:
            None

        """
        raise NotImplementedError

    def tracking_add_observer(self, observer: Callable, priority: int = 50) -> None:
        """Add an observer to the list of observers for tracking changes.

        This method registers a specified observer function to receive notifications
        about changes to a tracked object. Observers are notified in the order of
        their priority, with lower priority values indicating higher precedence.

        Args:
            observer: The function to be added as an observer.
            priority: The priority level of the observer.

        Returns:
            None

        """
        if priority not in self._tracking_observers:
            self._tracking_observers[priority] = []
        if (
            observer not in self._tracking_observers[priority]
            and observer != self._tracking_notify_observers
        ):
            self._tracking_observers[priority].append(observer)

    def tracking_remove_observer(self, observer: Callable) -> None:
        """Remove an observer from the list of observers for tracking changes.

        This method unregisters a previously added observer function, ensuring that
        it will no longer receive notifications about changes to tracked attributes.
        It searches through the priority levels to find and remove the observer.

        Args:
            observer: The function to be removed from the list of observers.

        Returns:
            None

        """
        for priority in self._tracking_observers:
            if observer in self._tracking_observers[priority]:
                self._tracking_observers[priority].remove(observer)

    def _tracking_notify_observers(self, change_log_entry: ChangeLogEntry) -> None:
        """Notify all observers of changes to a tracked object.

        This method iterates through the list of observers, sorted by priority, and
        notifies each observer of the provided change log entry. It ensures that all
        registered observers receive updates about changes, maintaining synchronization
        between the tracked objects and their observers.

        Args:
            change_log_entry: The change log entry that records changes to an object.

        Returns:
            None

        """
        priorities = sorted(self._tracking_observers.keys())
        for priority in priorities:
            for observer in self._tracking_observers[priority]:
                observer(change_log_entry)

    def tracking_add_change(self, change_log_entry: ChangeLogEntry) -> None:
        """Add a change log record to the list of changes.

        This method appends a new change log entry to the list of tracked changes
        for the instance. It ensures that the changes are sorted, maintaining the
        order of modifications for accurate tracking and retrieval.

        Args:
            change_log_entry: The change log entry to be added to the list of changes.

        Returns:
            None

        """
        self._tracking_changes.append(change_log_entry)
        self._tracking_changes.sort()

    def tracking_create_change(self, **kwargs) -> None:
        """Create a change log entry for the tracked object.

        This method generates a new change log entry based on the provided keyword
        arguments. It includes details such as the action performed, the state of
        the object before and after the change, and any additional context. The
        change log entry is then added to the list of tracked changes and observers
        are notified.

        Args:
            **kwargs: Additional keyword arguments to include in the change log entry.

        Returns:
            None

        """
        if "locked" not in kwargs:
            kwargs["locked"] = self._tracking_locked
        if "type" not in kwargs:
            kwargs["type"] = self._tracking_is_trackable(self)
        change_log_entry = ChangeLogEntry(self._tracking_uuid, **kwargs)
        change_log_entry.add_to_tree(
            self._tracking_format_tree_location(
                change_log_entry.extra.get("location", None)
            )
        )
        self._tracking_changes.append(change_log_entry)
        self._tracking_notify_observers(change_log_entry)

    def _tracking_format_tree_location(self, location: str = "") -> dict[str, str]:
        """Format the tree location for a change log entry.

        This method constructs a dictionary representing the location of the tracked
        object within the tracking structure. It includes the type of the object, its
        UUID, and the location within the hierarchy, formatted with the specified
        delimiter. It provides a way to format the information for better organization
        and visualization of tracked attributes.

        Args:
            location: The location of the tracked object within the hierarchy.

        Returns:
            A dictionary containing the type, UUID, and formatted location of the
            tracked object.

        """
        if location is not None:
            return {
                "type": self._tracking_is_trackable(self),
                "uuid": self._tracking_uuid,
                "location": f"{self._tracking_delimiter}{location}",
            }
        return {"type": self._tracking_is_trackable(self), "uuid": self._tracking_uuid}

    def lock(self) -> None:
        """Lock the instance and all child tracked items.

        This method sets the instance to a locked state, preventing modifications
        to its data. It also locks all child tracked items, ensuring that
        their values cannot be changed.

        Args:
            None

        Returns:
            None

        """
        self._tracking_locked = True
        for key in self._tracking_child_tracked_items:
            self._tracking_child_tracked_items[key]["item"].lock()
        self.tracking_create_change(action="lock")

    def unlock(self) -> None:
        """Unlock the instance and all child tracked items.

        This method sets the instance to an unlocked state, allowing modifications
        to its data. It also unlocks all child tracked items, ensuring that their
        values can be changed.

        Args:
            None

        Returns:
            None

        """
        self._tracking_locked = False
        for key in self._tracking_child_tracked_items:
            self._tracking_child_tracked_items[key]["item"].unlock()
        self.tracking_create_change(action="unlock")

    def tracking_get_formatted_updates(self) -> list[str]:
        """Retrieve a formatted list of the most recent changes.

        This method generates a formatted list of the most recent changes to the
        tracked object. It includes detailed information about each change, such as
        the action performed, the state of the object before and after the change,
        and any additional context. The formatted updates provide a comprehensive
        view of the modifications made to the object. It includes a separator for
        clarity and can be useful for logging or displaying the history of changes.

        Args:
            None

        Returns:
            A list of strings containing the formatted updates.

        """
        new_output = []
        for item in self._tracking_changes[:20]:
            # for item in self._tracking_changes:
            new_output.append("--------------------------------------")
            new_output.extend(item.format_detailed())
        new_output.append("--------------------------------------")
        return new_output

    def _tracking_convert_to_trackable(
        self,
        obj: Any,
        tracking_auto_converted_in: str | None = None,
        tracking_auto_convert: bool = False,
        tracking_parent: "TrackBase | None" = None,
        tracking_location: str | None = "",
    ) -> Any:
        """Convert an object to a trackable type if necessary.

        This method checks if the provided object is a dictionary or a list and
        converts it to a `TrackedDict` or `TrackedList` respectively, if it is not
        already trackable. It ensures that the object is appropriately formatted
        for tracking purposes, allowing for consistent monitoring of changes.

        Args:
            obj: The object to be converted to a trackable type.
            tracking_auto_converted_in: The context in which automatic conversion
            occurs.
            tracking_auto_convert: Flag indicating whether to automatically convert
            values.
            tracking_parent: An optional parent instance for establishing a hierarchy.
            tracking_location: The location of the tracked attribute.

        Returns:
            The converted trackable object, or the original object if no conversion
            is performed.

        """
        if isinstance(obj, dict) and not self._tracking_is_trackable(obj):
            from .trackeddict import TrackedDict

            return TrackedDict(
                obj,
                tracking_auto_converted_in=tracking_auto_converted_in,
                tracking_auto_convert=tracking_auto_convert or False,
                tracking_parent=tracking_parent,
                tracking_location=tracking_location,
            )
        if isinstance(obj, list) and not self._tracking_is_trackable(obj):
            from .trackedlist import TrackedList

            return TrackedList(
                obj,
                tracking_auto_converted_in=tracking_auto_converted_in,
                tracking_auto_convert=tracking_auto_convert or False,
                tracking_parent=tracking_parent,
                tracking_location=tracking_location,
            )
        return obj

    def _tracking_is_trackable(
        self, obj: Any
    ) -> (
        Literal["TrackedDict"]
        | Literal["TrackedList"]
        | Literal["TrackedAttr"]
        | Literal[""]
    ):
        """Check if an object is trackable.

        This method determines if the provided object is an instance of a trackable
        type, such as `TrackedDict`, `TrackedList`, or `TrackedAttr`. It returns a
        string representing the type of the trackable object, or an empty string if
        the object is not trackable.

        Args:
            obj: The object to check for trackability.

        Returns:
            A string indicating the type of the trackable object, or an empty string
            if the object is not trackable.

        """
        from .trackeddict import TrackedDict
        from .trackedlist import TrackedList
        from .trackedattributes import TrackedAttr

        if isinstance(obj, TrackedDict):
            return "TrackedDict"
        elif isinstance(obj, TrackedList):
            return "TrackedList"
        elif isinstance(obj, TrackedAttr):
            return "TrackedAttr"
        return ""

    def _tracking_convert_to_untrackable(self, obj: Any) -> Any:
        """Convert a trackable object to its untrackable form.

        This method checks if the provided object is a trackable type, such as
        `TrackedDict` or `TrackedList`, and converts it to its untrackable form.
        It recursively processes the object's elements, ensuring that all nested
        trackable items are also converted to their untrackable forms.

        Args:
            obj: The trackable object to be converted to an untrackable form.

        Returns:
            The untrackable form of the object, or the original object if it is not
            trackable.

        """
        from ..types.trackeddict import TrackedDict
        from ..types.trackedlist import TrackedList

        if self._tracking_is_trackable(obj):
            if isinstance(obj, TrackedDict):
                return {
                    item: self._tracking_convert_to_untrackable(obj[item])
                    for item in obj
                }
            if isinstance(obj, TrackedList):
                return [self._tracking_convert_to_untrackable(item) for item in obj]
        return obj
